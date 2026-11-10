#!/usr/bin/env python3
# encoding: utf-8
"""routeur_ordres.py — Étape 2 : SEUL programme qui comprend les phrases.

Toutes les sources écrivent la phrase sur /vocal_detect/asr_result :
  micro du robot, micro du PC (bouton de la page), zone de texte de la page,
  touches P / M / R / B de la page.
Le routeur la comprend (routeur_logique.py), puis :
  « stop » …        -> /robot/estop true   (le gardien verrouille aussi de lui-même)
  « reprends »      -> /robot/estop false
  ordre compris     -> /robot/ordre (JSON), un ordre à la fois, attend /robot/ordre/fin
  phrase inconnue   -> IA locale du PC (Ollama), réponse contrôlée ; si elle fait
                       bouger le robot : « Je vais … Je lance ? » puis « oui ».

Exécuteurs :
  avance / recule / crabe / tourne -> llm_move_bridge_node.py
  attrape                          -> pick_and_place_node_v6.py
  attrape_tout / patrouille        -> autonomous_mission_node.py
  etat                             -> ici

Publie aussi /robot/routeur/etat (JSON) pour la page : phrase reçue, ce qui a
été compris, étape en cours.
"""
import itertools
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
from std_msgs.msg import String, Bool, UInt16

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import routeur_logique as rl  # noqa: E402
from voix_rapide import VoixRapide  # noqa: E402

OLLAMA_URL = 'http://192.168.1.20:11434'
OLLAMA_MODELE = 'qwen3.5:9b'
IA_DELAI_S = 40.0          # le 1er appel charge le modèle (plus long)
CONFIRMATION_S = 20.0      # délai pour répondre « oui »
DOUBLON_S = 1.5            # même phrase reçue deux fois (deux micros) : ignorée

# Durée maximale d'attente de la fin de chaque ordre (au-delà : échec)
def delai_max(o):
    a = o['action']
    if a == 'avance':
        return o['distance_m'] / 0.20 * 3 + 8
    if a == 'recule':
        return o['distance_m'] / 0.10 * 3 + 8
    if a == 'crabe':
        return o['distance_m'] / 0.15 * 3 + 8
    if a == 'tourne':
        return abs(o['angle_deg']) / 30.0 + 8
    if a == 'attrape':
        return 150
    return 900   # missions

PHRASES_FIXES = [
    "Je n'ai pas compris.", "Je réfléchis.", "Je suis occupé. Dis stop pour annuler.",
    "Arrêt général actif. Dis reprends d'abord.", "D'accord, j'annule.",
    "J'avance.", "Je recule.", "Je me décale.", "Je tourne.", "C'est fait.",
    "Je n'ai pas pu terminer.", "Mon intelligence artificielle ne répond pas.",
]
ANNONCE = {'avance': "J'avance.", 'recule': "Je recule.", 'crabe': "Je me décale.",
           'tourne': "Je tourne."}


class RouteurOrdres(Node):
    def __init__(self):
        super().__init__('routeur_ordres')
        self.declare_parameter('ollama_url', OLLAMA_URL)
        self.declare_parameter('ollama_modele', OLLAMA_MODELE)

        self._lock = threading.Lock()
        self._verrou = False
        self._plan_en_cours = None       # liste d'ordres
        self._attente = None             # (plan, heure limite) en attente de « oui »
        self._fin = {}                   # id -> message de fin
        self._fin_evt = threading.Event()
        self._annuler = False
        self._ids = itertools.count(1)
        self._dernier = ('', 0.0)
        self._batterie_mv = 0
        self._securite = {}
        self._etat = {'texte': '', 'compris': '', 'source': '', 'etat': 'libre', 'dit': ''}

        latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                             reliability=ReliabilityPolicy.RELIABLE)
        self.pub_ordre = self.create_publisher(String, '/robot/ordre', 10)
        self.pub_estop = self.create_publisher(Bool, '/robot/estop', 10)
        self.pub_tts = self.create_publisher(String, '/tts_node/tts_text', 1)
        self.pub_etat = self.create_publisher(String, '/robot/routeur/etat', latched)

        self.create_subscription(String, '/vocal_detect/asr_result', self._asr_cb, 10)
        self.create_subscription(String, '/robot/ordre/fin', self._fin_cb, 10)
        self.create_subscription(Bool, '/robot/estop_etat', self._estop_cb, latched)
        self.create_subscription(UInt16, '/ros_robot_controller/battery', self._batt_cb, 1)
        self.create_subscription(String, '/robot/securite/etat', self._secu_cb, 1)

        self.voix = VoixRapide(PHRASES_FIXES, repli=self._dire_tts,
                               journal=lambda m: self.get_logger().info(m))
        self.create_timer(1.0, self._publier_etat)
        self.get_logger().info('routeur_ordres prêt (étape 2) — une seule porte d\'entrée pour les phrases')

    # ── entrées ──
    def _asr_cb(self, msg):
        texte = msg.data.strip()
        if not texte:
            return
        now = time.monotonic()
        if texte == self._dernier[0] and now - self._dernier[1] < DOUBLON_S:
            return
        self._dernier = (texte, now)
        self.get_logger().info(f'🎤 « {texte} »')
        threading.Thread(target=self._traiter, args=(texte,), daemon=True).start()

    def _fin_cb(self, msg):
        try:
            f = json.loads(msg.data)
        except ValueError:
            return
        with self._lock:
            self._fin[f.get('id')] = f
        self._fin_evt.set()

    def _estop_cb(self, msg):
        self._verrou = bool(msg.data)
        if msg.data:
            with self._lock:
                self._attente = None
                if self._plan_en_cours:
                    self._annuler = True
            self._fin_evt.set()

    def _batt_cb(self, msg):
        self._batterie_mv = msg.data

    def _secu_cb(self, msg):
        try:
            self._securite = json.loads(msg.data)
        except ValueError:
            pass

    # ── compréhension ──
    def _traiter(self, texte):
        with self._lock:
            attente = self._attente
            if attente and time.monotonic() > attente[1]:
                self._attente = attente = None
        r = rl.analyser(texte, attente_confirmation=attente is not None)
        source = 'grammaire'
        self._maj(texte=texte, compris='', source='')

        if r.genre == 'arret':
            self._maj(compris='arrêt général', source=source)
            self.pub_estop.publish(Bool(data=True))
            return
        if r.genre == 'reprise':
            self._maj(compris='reprise', source=source)
            self.pub_estop.publish(Bool(data=False))
            return
        if r.genre == 'confirme':
            with self._lock:
                self._attente = None
            self._maj(compris='oui : ' + rl.decrire_plan(attente[0]), source='ia')
            self._lancer(attente[0])
            return
        if r.genre == 'infirme':
            with self._lock:
                self._attente = None
            self._maj(compris='non : annulé', source=source)
            self._dire("D'accord, j'annule.")
            return

        if r.genre == 'inconnu':
            source = 'ia'
            self._maj(compris='… demande à l\'IA', source=source, etat='réflexion')
            self._dire("Je réfléchis.")
            r = self._demander_ia(texte)
            if r is None:
                self._maj(compris='IA injoignable', etat=self._etat_courant())
                self._dire("Mon intelligence artificielle ne répond pas.")
                return

        if r.genre in ('parole', 'refus'):
            self._maj(compris=('réponse : ' if r.genre == 'parole' else 'refus : ') + r.message,
                      source=source, etat=self._etat_courant())
            self._dire(r.message)
            return

        # r.genre == 'plan'
        if source == 'ia' and rl.est_long(r.plan):
            with self._lock:
                self._attente = (r.plan, time.monotonic() + CONFIRMATION_S)
            self._maj(compris=rl.decrire_plan(r.plan), source=source, etat='attente du oui')
            self._dire(f"Je vais {rl.decrire_plan(r.plan)}. Je lance ?")
            return
        self._maj(compris=rl.decrire_plan(r.plan), source=source)
        self._lancer(r.plan)

    def _demander_ia(self, texte):
        url = self.get_parameter('ollama_url').value.rstrip('/') + '/api/chat'
        corps = {
            'model': self.get_parameter('ollama_modele').value,
            'messages': [{'role': 'system', 'content': rl.CONSIGNE_IA},
                         {'role': 'user', 'content': texte}],
            'format': rl.SCHEMA_IA, 'stream': False, 'think': False,
            'options': {'temperature': 0}, 'keep_alive': '30m',
        }
        t0 = time.monotonic()
        for essai in (1, 2):
            try:
                req = urllib.request.Request(url, data=json.dumps(corps).encode(),
                                             headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(req, timeout=IA_DELAI_S) as rep:
                    contenu = json.loads(rep.read())['message']['content']
                self.get_logger().info(f'🧠 IA ({time.monotonic() - t0:.1f} s) : {contenu[:200]}')
                try:
                    obj = json.loads(contenu)
                except ValueError:
                    obj = None
                return rl.valider_plan_ia(obj)
            except urllib.error.HTTPError as e:
                # Modèle sans mode « think » : on réessaie sans ce champ
                if essai == 1 and e.code == 400:
                    corps.pop('think', None)
                    continue
                self.get_logger().warn(f'IA : erreur HTTP {e.code}')
                return None
            except Exception as e:
                self.get_logger().warn(f'IA injoignable ({url}) : {e}')
                return None
        return None

    # ── exécution ──
    def _lancer(self, plan):
        with self._lock:
            if self._plan_en_cours:
                occupe = True
            else:
                occupe = False
                self._plan_en_cours = plan
                self._annuler = False
        if occupe:
            self._dire("Je suis occupé. Dis stop pour annuler.")
            return
        if self._verrou and any(o['action'] != 'etat' for o in plan):
            with self._lock:
                self._plan_en_cours = None
            self._dire("Arrêt général actif. Dis reprends d'abord.")
            return
        try:
            n = len(plan)
            for i, o in enumerate(plan, 1):
                if self._annuler:
                    break
                self._maj(etat=f'étape {i}/{n} : {rl.decrire(o)}')
                if o['action'] == 'etat':
                    self._dire(self._phrase_etat())
                    continue
                if o['action'] in ANNONCE:
                    self._dire(ANNONCE[o['action']])
                res = self._executer(o)
                self.get_logger().info(f'  étape {i}/{n} {o["action"]} -> {res}')
                if res.get('resultat') != 'ok':
                    # Le pick et la mission annoncent eux-mêmes leurs échecs
                    if res.get('resultat') != 'annule' and not self._annuler \
                            and o['action'] in ANNONCE:
                        detail = res.get('detail', '')
                        self._dire(f"Je n'ai pas pu terminer : {detail}." if detail
                                   else "Je n'ai pas pu terminer.")
                    break
            else:
                if plan[-1]['action'] in ANNONCE:
                    self._dire("C'est fait.")
        finally:
            with self._lock:
                self._plan_en_cours = None
            self._maj(etat=self._etat_courant())

    def _executer(self, o):
        oid = f'r{next(self._ids)}'
        ordre = dict(o, id=oid)
        with self._lock:
            self._fin.pop(oid, None)
        self.pub_ordre.publish(String(data=json.dumps(ordre, ensure_ascii=False)))
        limite = time.monotonic() + delai_max(o)
        while time.monotonic() < limite:
            self._fin_evt.wait(0.2)
            self._fin_evt.clear()
            with self._lock:
                f = self._fin.pop(oid, None)
            if f:
                return f
            if self._annuler:
                return {'resultat': 'annule'}
        return {'resultat': 'echec', 'detail': 'pas de réponse du programme chargé de cet ordre'}

    # ── sorties ──
    def _phrase_etat(self):
        mv = self._batterie_mv
        batt = (f"Batterie : {mv / 1000:.1f} volts".replace('.', ',') if mv
                else "Batterie inconnue")
        if self._verrou:
            secu = "Arrêt général actif."
        elif not self._securite:
            secu = "Gardien de sécurité muet."
        elif not self._securite.get('lidar_ok', False):
            secu = "Lidar muet."
        else:
            secu = "Sécurité : OK."
        return f"{batt}. {secu}"

    def _etat_courant(self):
        if self._plan_en_cours:
            return 'exécution'
        if self._attente:
            return 'attente du oui'
        return 'libre'

    def _dire(self, texte):
        self.get_logger().info(f'🗣️  {texte}')
        self._maj(dit=texte)
        self.voix.dire(texte)

    def _dire_tts(self, texte):
        self.pub_tts.publish(String(data=texte))

    def _maj(self, **champs):
        with self._lock:
            self._etat.update(champs)
        self._publier_etat()

    def _publier_etat(self):
        with self._lock:
            e = dict(self._etat)
        self.pub_etat.publish(String(data=json.dumps(e, ensure_ascii=False)))


def main():
    rclpy.init()
    node = RouteurOrdres()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
