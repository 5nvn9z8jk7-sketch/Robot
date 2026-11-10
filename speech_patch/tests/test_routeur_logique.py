# Tests hors robot de la compréhension des ordres (étape 2).
# Chaque ligne : phrase telle qu'elle arrive (micro ou clavier) -> ce qui doit être compris.
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import routeur_logique as rl  # noqa: E402


def av(d):
    return {'action': 'avance', 'distance_m': d}


def re_(d):
    return {'action': 'recule', 'distance_m': d}


def cr(c, d):
    return {'action': 'crabe', 'cote': c, 'distance_m': d}


def to(a):
    return {'action': 'tourne', 'angle_deg': a}


ROUGE = {'action': 'attrape', 'couleur': 'rouge'}
TOUT = {'action': 'attrape_tout'}

PLANS = [
    # avance
    ("avance", [av(0.5)]),
    ("Avance de 50 cm", [av(0.5)]),
    ("avance de cinquante centimètres", [av(0.5)]),
    ("Robot, avance d'un mètre !", [av(1.0)]),
    ("avance de 1,5 mètre", [av(1.5)]),
    ("avance de 1.5 m", [av(1.5)]),
    ("avance d'un mètre et demi", [av(1.5)]),
    ("avance de un mètre cinquante", [av(1.5)]),
    ("avance d'un demi mètre", [av(0.5)]),
    ("avance de deux mètres", [av(2.0)]),
    ("avance un peu", [av(0.2)]),
    ("avance pendant 3 secondes", [av(0.6)]),
    ("va tout droit sur trente centimètres", [av(0.3)]),
    ("avance de vingt-cinq centimètres", [av(0.25)]),
    # recule
    ("recule", [re_(0.3)]),
    ("recule de 20 cm", [re_(0.2)]),
    ("recule de quarante centimètres", [re_(0.4)]),
    ("Recule un peu.", [re_(0.1)]),
    # crabe
    ("décale-toi à gauche", [cr('gauche', 0.3)]),
    ("décale toi à droite de 20 centimètres", [cr('droite', 0.2)]),
    ("glisse à gauche de 50 cm", [cr('gauche', 0.5)]),
    ("crabe droite 1 mètre", [cr('droite', 1.0)]),
    ("va de côté à droite", [cr('droite', 0.3)]),
    # tourne
    ("tourne à gauche", [to(90.0)]),
    ("tourne à droite", [to(-90.0)]),
    ("Tourne à droite de 45 degrés", [to(-45.0)]),
    ("tourne de quatre-vingt-dix degrés à gauche", [to(90.0)]),
    ("tourne à gauche de 30°", [to(30.0)]),
    ("fais demi-tour", [to(180.0)]),
    ("fais un quart de tour à droite", [to(-90.0)]),
    ("pivote à droite de cent quatre-vingts degrés", [to(-180.0)]),
    ("tourne un peu à gauche", [to(20.0)]),
    ("gauche", [to(90.0)]),
    ("fais un tour complet", [to(360.0)]),
    ("tourne à droite de soixante-dix degrés", [to(-70.0)]),
    # attraper
    ("attrape le cube rouge", [ROUGE]),
    ("Attrape le cube rouge", [ROUGE]),
    ("prends le cube", [ROUGE]),
    ("va chercher le bloc rouge", [ROUGE]),
    ("ramasse le cube", [ROUGE]),
    ("attrape tous les cubes", [TOUT]),
    ("mission attrape tous les cubes", [TOUT]),
    ("ramasse les cubes rouges", [TOUT]),
    ("patrouille", [{'action': 'patrouille'}]),
    # état
    ("état", [{'action': 'etat'}]),
    ("status", [{'action': 'etat'}]),
    ("quel est ton niveau de batterie", [{'action': 'etat'}]),
    # enchaînements
    ("avance de 1 mètre puis tourne à droite", [av(1.0), to(-90.0)]),
    ("avance de 50 cm et tourne à gauche", [av(0.5), to(90.0)]),
    ("tourne à gauche, ensuite avance de 30 centimètres puis attrape le cube rouge",
     [to(90.0), av(0.3), ROUGE]),
    ("recule de 20 cm puis décale-toi à droite", [re_(0.2), cr('droite', 0.3)]),
]


@pytest.mark.parametrize('phrase,plan', PLANS)
def test_plans(phrase, plan):
    r = rl.analyser(phrase)
    assert r.genre == 'plan', r
    assert r.plan == plan


@pytest.mark.parametrize('phrase', ["stop", "Stop !", "arrête-toi", "arrête", "halte",
                                    "ne bouge plus", "annule", "pause",
                                    "avance puis arrête"])
def test_arret(phrase):
    assert rl.analyser(phrase).genre == 'arret'


@pytest.mark.parametrize('phrase', ["reprends", "tu peux repartir", "reprise"])
def test_reprise(phrase):
    assert rl.analyser(phrase).genre == 'reprise'


@pytest.mark.parametrize('phrase', [
    "recule d'un mètre",            # arrière non surveillé : 0,5 m maximum
    "avance de dix mètres",
    "décale-toi à gauche de deux mètres",
    "tourne à gauche de 720 degrés",
    "attrape le cube bleu",          # seul le rouge est reconnu par la caméra
    "dépose le cube dans le bac",    # étape 3
    "retourne à la base",            # étape 4
    "va à la cuisine",               # étape 4
    "ouvre la pince",
    "décale-toi",                    # côté manquant
    "avance de 0 cm",
])
def test_refus(phrase):
    r = rl.analyser(phrase)
    assert r.genre == 'refus', r
    assert r.message


@pytest.mark.parametrize('phrase', ["bonjour", "Dis bonjour au robot", "merci",
                                    "Présente-toi, qui es-tu ?",
                                    "Demande au robot comment ça va"])
def test_parole(phrase):
    r = rl.analyser(phrase)
    assert r.genre == 'parole' and r.message


@pytest.mark.parametrize('phrase', ["", "quelle heure est-il", "raconte une blague",
                                    "regarde le cube", "trouve la balle rouge",
                                    "approche-toi de la chaise"])
def test_inconnu_va_a_l_ia(phrase):
    assert rl.analyser(phrase).genre == 'inconnu'


def test_confirmation():
    assert rl.analyser("oui", attente_confirmation=True).genre == 'confirme'
    assert rl.analyser("ok vas-y", attente_confirmation=True).genre == 'confirme'
    assert rl.analyser("non", attente_confirmation=True).genre == 'infirme'
    assert rl.analyser("annule", attente_confirmation=True).genre == 'infirme'
    assert rl.analyser("stop", attente_confirmation=True).genre == 'arret'
    assert rl.analyser("oui").genre == 'inconnu'   # hors confirmation : rien


def test_normalisation_nombres():
    n = rl.normaliser
    assert n("quatre-vingt-dix") == "90"
    assert n("soixante et onze") == "71"
    assert n("vingt et un") == "21"
    assert n("cent cinquante") == "150"
    assert n("trois cent soixante degrés") == "360 degres"
    assert n("dix-sept") == "17"
    assert n("Robot, avance d'1,5 m") == "avance d 1.5 m"


def test_trop_d_etapes():
    r = rl.analyser("avance puis recule puis avance puis recule puis avance puis recule")
    assert r.genre == 'refus'


# ── réponses de l'IA ──

def test_ia_plan_valide():
    r = rl.valider_plan_ia({'plan': [{'action': 'avance', 'distance_m': 0.4},
                                     {'action': 'tourne', 'angle_deg': -45}],
                            'reponse': "J'avance puis je tourne."})
    assert r.genre == 'plan'
    assert r.plan == [av(0.4), to(-45.0)]


@pytest.mark.parametrize('obj', [
    None, "texte", {'plan': 'avance'},
    {'plan': [{'action': 'saute'}], 'reponse': ''},             # action inventée
    {'plan': [{'action': 'avance', 'distance_m': 8}], 'reponse': ''},
    {'plan': [{'action': 'recule', 'distance_m': 2}], 'reponse': ''},
    {'plan': [{'action': 'avance'}], 'reponse': ''},             # distance absente
    {'plan': [{'action': 'avance', 'distance_m': 'loin'}], 'reponse': ''},
    {'plan': [{'action': 'crabe', 'cote': 'haut', 'distance_m': 0.2}], 'reponse': ''},
    {'plan': [{'action': 'attrape', 'couleur': 'bleu'}], 'reponse': ''},
    {'plan': [{'action': 'tourne', 'angle_deg': 0}], 'reponse': ''},
    {'plan': [{'action': 'etat'}] * 6, 'reponse': ''},
    {'plan': [], 'reponse': ''},
])
def test_ia_refus(obj):
    assert rl.valider_plan_ia(obj).genre == 'refus'


def test_ia_conversation():
    r = rl.valider_plan_ia({'plan': [], 'reponse': 'Il fait beau.'})
    assert r.genre == 'parole' and r.message == 'Il fait beau.'


def test_descriptions():
    assert rl.decrire(av(0.5)) == 'avancer de 50 centimètres'
    assert rl.decrire(av(1.5)) == 'avancer de 1,5 mètre'
    assert rl.decrire(av(2.0)) == 'avancer de 2 mètres'
    assert rl.decrire(to(-45.0)) == 'tourner à droite de 45 degrés'
    assert rl.decrire(cr('gauche', 0.3)) == 'me décaler à gauche de 30 centimètres'
    assert rl.decrire_plan([av(1.0), to(90.0)]) == 'avancer de 1 mètre, puis tourner à gauche de 90 degrés'
