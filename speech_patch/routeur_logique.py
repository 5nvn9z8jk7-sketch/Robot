# encoding: utf-8
"""routeur_logique.py — Compréhension des ordres (étape 2), SANS ROS.

Une phrase (micro du robot, micro du PC ou zone de texte de la page)
  -> normalisation (minuscules, accents, nombres en lettres -> chiffres)
  -> grammaire fixe (avance 50 cm, tourne à droite de 45 degrés, attrape le cube…)
  -> sinon : « inconnu » (le nœud routeur_ordres.py demande alors à l'IA locale,
     dont la réponse est contrôlée ici par valider_plan_ia()).

Tout est testable sur PC : speech_patch/tests/test_routeur_logique.py

Conventions robot (vérifiées au clavier) : linear.x > 0 = avance,
linear.y > 0 = crabe à gauche, angular.z > 0 = tourne à gauche.
Ici : angle_deg > 0 = gauche, < 0 = droite.
"""
import re
import unicodedata

import securite_logique as sl

# ── Limites (refus au-delà, jamais de « rabotage » silencieux) ──
AVANCE_MAX_M = 3.0
RECUL_MAX_M = 0.40       # arrière non surveillé par le lidar (gardien : 0,10 m/s pendant 5 s au plus)
CRABE_MAX_M = 1.0
ANGLE_MAX_DEG = 360.0
ETAPES_MAX = 5           # ordres enchaînés par « puis »

# Valeurs quand la phrase ne donne pas de quantité
AVANCE_DEFAUT_M = 0.5
RECUL_DEFAUT_M = 0.3
CRABE_DEFAUT_M = 0.3
ANGLE_DEFAUT_DEG = 90.0
UN_PEU = {'avance': 0.2, 'recule': 0.1, 'crabe': 0.1, 'tourne': 20.0}

# Vitesses servant à convertir « pendant N secondes » (les mêmes que l'exécuteur)
VITESSE = {'avance': 0.20, 'recule': 0.10, 'crabe': 0.15}

COULEURS = ['rouge', 'bleu', 'vert', 'jaune', 'orange', 'violet', 'rose', 'noir', 'blanc']
COULEURS_OK = ['rouge']

ACTIONS = ('avance', 'recule', 'crabe', 'tourne', 'attrape', 'attrape_tout',
           'patrouille', 'etat')

# ── Normalisation ──

_NOMBRES = {
    'zero': 0, 'un': 1, 'une': 1, 'deux': 2, 'trois': 3, 'quatre': 4, 'cinq': 5,
    'six': 6, 'sept': 7, 'huit': 8, 'neuf': 9, 'dix': 10, 'onze': 11, 'douze': 12,
    'treize': 13, 'quatorze': 14, 'quinze': 15, 'seize': 16, 'vingt': 20, 'vingts': 20,
    'trente': 30, 'quarante': 40, 'cinquante': 50, 'soixante': 60,
    'cent': 100, 'cents': 100, 'mille': 1000,
}

MOTS_REVEIL = ['robot', 'robo', 'hiwonder', 'rosorin', 'hey', 'dis']


def _sans_accents(t):
    t = unicodedata.normalize('NFD', t)
    return ''.join(c for c in t if unicodedata.category(c) != 'Mn')


def _convertir_nombres(mots):
    """['quatre','vingt','dix','degres'] -> ['90','degres'] ; garde les autres mots."""
    sortie, i = [], 0
    while i < len(mots):
        if mots[i] not in _NOMBRES:
            sortie.append(mots[i])
            i += 1
            continue
        total, courant, j = 0, 0, i
        while j < len(mots):
            m = mots[j]
            if m == 'et' and j + 1 < len(mots) and mots[j + 1] in ('un', 'une', 'onze') \
                    and courant % 10 == 0 and courant >= 20:
                j += 1           # « vingt et un », « soixante et onze »
                continue
            if m not in _NOMBRES:
                break
            v = _NOMBRES[m]
            if v == 100:
                courant = (courant or 1) * 100
            elif v == 1000:
                total += (courant or 1) * 1000
                courant = 0
            elif v == 20 and courant % 100 == 4:
                courant += 76    # quatre-vingt(s)
            elif v < 10 and courant % 10 != 0:
                break            # « un deux » : deux nombres séparés
            else:
                courant += v
            j += 1
        sortie.append(str(total + courant))
        i = j
    return sortie


def normaliser(texte):
    """« Robot, avance d'un mètre et demi ! » -> « avance d 1 metre et demi »."""
    t = texte.lower().replace('°', ' degres ')
    t = re.sub(r'(\d)[,.](\d)', r'\1#\2', t)       # 1,5 -> 1#5 (protégé)
    t = _sans_accents(t)
    t = ''.join(c if (c.isalnum() or c == '#') else ' ' for c in t)
    t = t.replace('#', '.')
    mots = t.split()
    while mots and mots[0] in MOTS_REVEIL:          # « robot, … », « ok robot … »
        mots = mots[1:]
    return ' '.join(_convertir_nombres(mots))


# ── Résultat ──

class Resultat:
    """genre : 'plan' | 'arret' | 'reprise' | 'confirme' | 'infirme' | 'parole' | 'refus' | 'inconnu'"""

    def __init__(self, genre, plan=None, message=''):
        self.genre = genre
        self.plan = plan or []
        self.message = message

    def __repr__(self):
        return f'Resultat({self.genre!r}, {self.plan!r}, {self.message!r})'


# ── Grammaire ──

_NB = r'(\d+(?:\.\d+)?)'
_V_AVANCE = r'\b(avance[sz]?|avancer|en avant|tout droit|marche avant|va devant)\b'
_V_RECULE = r'\b(recule[sz]?|reculer|en arriere|marche arriere)\b'
_V_CRABE = r'\b(decale[sz]?|decaler|glisse[sz]?|glisser|crabe|lateral|pas chasse)\b'
_V_TOURNE = r'\b(tourne[sz]?|tourner|pivote[sz]?|pivoter|virage|demi tour|quart de tour|fais 1 tour|un tour)\b'
_V_ATTRAPE = r'\b(attrape[sz]?|attraper|ramasse[sz]?|ramasser|prends|prendre|saisis|saisir|va chercher|recupere[sz]?|recuperer)\b'
_OBJET = r'\b(cube|cubes|bloc|blocs)\b'

SALUTATIONS = [
    ('qui es tu', "Je suis le robot ROSOrin. Je peux avancer, tourner, me décaler et attraper le cube rouge."),
    ('presente toi', "Je suis le robot ROSOrin. Je peux avancer, tourner, me décaler et attraper le cube rouge."),
    ('comment ca va', "Ça va très bien, merci."),
    ('comment vas tu', "Ça va très bien, merci."),
    ('bonjour', "Bonjour. Je t'écoute."),
    ('salut', "Salut. Je t'écoute."),
    ('coucou', "Coucou."),
    ('merci', "Avec plaisir."),
]

MOTS_OUI = ['oui', 'vas y', 'd accord', 'ok', 'confirme', 'go', 'c est parti', 'lance']
MOTS_NON = ['non', 'annule', 'laisse tomber', 'pas maintenant', 'oublie']
MOTS_ANNULE = ['annule', 'annuler', 'pause', 'cancel']   # hors confirmation = arrêt

_SEPARATEURS = r'\s+(?:puis|ensuite|et puis|et ensuite|apres ca|apres)\s+'
_VERBES_DEBUT = ('tourne', 'avance', 'recule', 'decale', 'glisse', 'attrape', 'ramasse',
                 'prends', 'pivote', 'fais', 'va', 'reviens', 'donne', 'dis')


def _a(expr, t):
    return f' {expr} ' in f' {t} '


def _distance(t, action):
    """Distance en mètres trouvée dans le segment, ou None."""
    m = re.search(_NB + r'\s*(?:metres?|m)\b(?:\s+(\d{1,2})\b(?!\s*(?:cm|centimetres?|degres?)))?', t)
    if m:
        d = float(m.group(1))
        if m.group(2):                       # « 1 metre 50 »
            d += int(m.group(2)) / 100.0
        if re.search(r'(?:metres?|m)\s+et\s+demi', t[m.start():]):
            d += 0.5
        return d
    m = re.search(_NB + r'\s*(?:cm|centimetres?|centimetre)\b', t)
    if m:
        return float(m.group(1)) / 100.0
    if re.search(r'\bdemi metre\b', t):
        return 0.5
    m = re.search(_NB + r'\s*(?:secondes?|sec|s)\b', t)
    if m and action in VITESSE:
        return round(float(m.group(1)) * VITESSE[action], 3)
    if re.search(r'\b(1 peu|un peu|legerement|doucement 1 peu)\b', t):
        return UN_PEU[action]
    return None


def _cote(t):
    g = re.search(r'\bgauche\b', t)
    d = re.search(r'\bdroite\b', t)
    if g and not d:
        return 'gauche'
    if d and not g:
        return 'droite'
    return None


def _angle(t):
    if re.search(r'\bdemi tour\b', t):
        return 180.0
    if re.search(r'\bquart de tour\b', t):
        return 90.0
    m = re.search(_NB + r'\s*(?:degres?|deg)\b', t)
    if m:
        return float(m.group(1))
    if re.search(r'\b(1 tour|un tour|tour complet)\b', t):
        return 360.0
    if re.search(r'\b(1 peu|un peu|legerement)\b', t):
        return UN_PEU['tourne']
    return None


def _refus_limite(action, valeur):
    if action == 'avance' and valeur > AVANCE_MAX_M:
        return f"C'est trop loin : j'avance de {_fmt_m(AVANCE_MAX_M)} au maximum."
    if action == 'recule' and valeur > RECUL_MAX_M:
        return (f"Je recule de {_fmt_m(RECUL_MAX_M)} au maximum, "
                "car je ne vois pas derrière moi.")
    if action == 'crabe' and valeur > CRABE_MAX_M:
        return f"Je me décale de {_fmt_m(CRABE_MAX_M)} au maximum."
    if action == 'tourne' and abs(valeur) > ANGLE_MAX_DEG:
        return "Je tourne d'un tour complet au maximum."
    if valeur <= 0:
        return "Il me faut une valeur plus grande que zéro."
    return None


def _segment(t):
    """Un ordre simple -> dict, ou Resultat (refus / parole), ou None (inconnu)."""
    # Attraper (avant les déplacements : « va chercher le cube » n'est pas « va »)
    if re.search(_V_ATTRAPE, t) and re.search(_OBJET, t):
        if re.search(r'\b(tous|tout|toutes|les cubes|les blocs)\b', t):
            return {'action': 'attrape_tout'}
        couleur = next((c for c in COULEURS if re.search(rf'\b{c}s?\b', t)), 'rouge')
        if couleur not in COULEURS_OK:
            return Resultat('refus', message="Pour l'instant, je sais seulement attraper le cube rouge.")
        return {'action': 'attrape', 'couleur': couleur}
    if re.search(r'\b(mission|collecte|ramasse tout|attrape tout)\b', t):
        return {'action': 'attrape_tout'}
    if re.search(r'\b(patrouille|patrouiller|fais 1 ronde|fais une ronde|ronde)\b', t):
        return {'action': 'patrouille'}

    # Pas encore disponibles (réponse claire au lieu d'un geste au hasard)
    if re.search(r'\b(depose|deposer|pose le|pose la|lache|mets le|mets la)\b', t):
        return Resultat('refus', message="La dépose dans le bac n'est pas encore disponible.")
    if re.search(r'\b(base|maison|recharge toi|va te charger)\b', t) and \
            re.search(r'\b(retourne|rentre|reviens|va|retour)\b', t):
        return Resultat('refus', message="Le retour à la base n'est pas encore disponible : il me faut d'abord une carte.")
    if re.search(r'\bva (?:a|au|aux|dans|vers|jusqu)\b', t) and not re.search(r'\b(gauche|droite)\b', t):
        return Resultat('refus', message="Je ne connais pas encore les lieux : il me faut d'abord une carte.")
    if re.search(r'\b(ouvre|ferme)\b', t) and re.search(r'\bpince\b', t):
        return Resultat('refus', message="La pince seule n'est pas encore disponible. Dis : attrape le cube rouge.")

    # Déplacements
    cote = _cote(t)
    if re.search(_V_CRABE, t) or (cote and re.search(r'\bde cote\b', t)):
        if not cote:
            return Resultat('refus', message="Je me décale à gauche ou à droite ?")
        d = _distance(t, 'crabe')
        d = CRABE_DEFAUT_M if d is None else d
        refus = _refus_limite('crabe', d)
        return Resultat('refus', message=refus) if refus else {'action': 'crabe', 'cote': cote, 'distance_m': d}
    if re.search(_V_TOURNE, t) or (cote and not re.search(_V_AVANCE + '|' + _V_RECULE, t)):
        a = _angle(t)
        a = ANGLE_DEFAUT_DEG if a is None else a
        signe = -1.0 if cote == 'droite' else 1.0
        refus = _refus_limite('tourne', a)
        return Resultat('refus', message=refus) if refus else {'action': 'tourne', 'angle_deg': signe * a}
    if re.search(_V_RECULE, t):
        d = _distance(t, 'recule')
        d = RECUL_DEFAUT_M if d is None else d
        refus = _refus_limite('recule', d)
        return Resultat('refus', message=refus) if refus else {'action': 'recule', 'distance_m': d}
    if re.search(_V_AVANCE, t):
        d = _distance(t, 'avance')
        d = AVANCE_DEFAUT_M if d is None else d
        refus = _refus_limite('avance', d)
        return Resultat('refus', message=refus) if refus else {'action': 'avance', 'distance_m': d}

    # État
    if re.search(r'\b(etat|status|statut|batterie|rapport|ou en es tu)\b', t):
        return {'action': 'etat'}
    return None


def _decouper(t):
    morceaux = re.split(_SEPARATEURS, t)
    sortie = []
    for m in morceaux:
        # « … et tourne … » : coupe sur « et » seulement devant un verbe d'action
        sortie.extend(re.split(r'\s+et\s+(?=(?:' + '|'.join(_VERBES_DEBUT) + r')\w*\b)', m))
    return [s.strip() for s in sortie if s.strip()]


def analyser(texte, attente_confirmation=False):
    """Phrase brute -> Resultat."""
    t = normaliser(texte)
    if not t:
        return Resultat('inconnu')
    # 1) Arrêt : mêmes mots que le gardien (qui verrouille de son côté de toute façon)
    if sl.est_arret(texte):
        return Resultat('arret')
    if sl.est_reprise(texte):
        return Resultat('reprise')
    # 2) Réponse à « Je lance ? »
    if attente_confirmation:
        if any(_a(m, t) for m in MOTS_NON):
            return Resultat('infirme')
        if any(_a(m, t) for m in MOTS_OUI):
            return Resultat('confirme')
    if any(_a(m, t) for m in MOTS_ANNULE):
        return Resultat('arret')
    # 3) Grammaire fixe, éventuellement enchaînée par « puis »
    segments = _decouper(t)
    plan = []
    for s in segments:
        r = _segment(s)
        if r is None:
            break
        if isinstance(r, Resultat):
            return r
        plan.append(r)
    else:
        if len(plan) > ETAPES_MAX:
            return Resultat('refus', message=f"C'est trop long : {ETAPES_MAX} ordres à la suite au maximum.")
        if plan:
            return Resultat('plan', plan)
    # 4) Politesse (seulement si rien d'autre n'a été compris)
    for cle, reponse in SALUTATIONS:
        if _a(cle, t):
            return Resultat('parole', message=reponse)
    return Resultat('inconnu')


# ── Repli IA : contrôle strict de la réponse ──

def valider_plan_ia(obj):
    """Réponse JSON de l'IA -> Resultat. Tout écart -> refus (rien n'est exécuté)."""
    if not isinstance(obj, dict):
        return Resultat('refus', message="Je n'ai pas compris.")
    reponse = obj.get('reponse', '')
    reponse = reponse.strip() if isinstance(reponse, str) else ''
    plan_brut = obj.get('plan', [])
    if not isinstance(plan_brut, list):
        return Resultat('refus', message="Je n'ai pas compris.")
    if not plan_brut:
        return Resultat('parole', message=reponse[:300]) if reponse else \
            Resultat('refus', message="Je n'ai pas compris.")
    if len(plan_brut) > ETAPES_MAX:
        return Resultat('refus', message=f"C'est trop long : {ETAPES_MAX} ordres à la suite au maximum.")
    plan = []
    for e in plan_brut:
        if not isinstance(e, dict) or e.get('action') not in ACTIONS:
            return Resultat('refus', message="Je ne sais pas encore faire ça.")
        a = e['action']
        try:
            if a in ('avance', 'recule'):
                d = float(e['distance_m'])
                refus = _refus_limite(a, d)
                if refus:
                    return Resultat('refus', message=refus)
                plan.append({'action': a, 'distance_m': round(d, 3)})
            elif a == 'crabe':
                d = float(e['distance_m'])
                if e.get('cote') not in ('gauche', 'droite'):
                    return Resultat('refus', message="Je n'ai pas compris de quel côté.")
                refus = _refus_limite(a, d)
                if refus:
                    return Resultat('refus', message=refus)
                plan.append({'action': a, 'cote': e['cote'], 'distance_m': round(d, 3)})
            elif a == 'tourne':
                ang = float(e['angle_deg'])
                if ang == 0:
                    return Resultat('refus', message="Je n'ai pas compris de combien tourner.")
                refus = _refus_limite(a, abs(ang))
                if refus:
                    return Resultat('refus', message=refus)
                plan.append({'action': a, 'angle_deg': round(ang, 1)})
            elif a == 'attrape':
                c = e.get('couleur', 'rouge') or 'rouge'
                if c not in COULEURS_OK:
                    return Resultat('refus', message="Pour l'instant, je sais seulement attraper le cube rouge.")
                plan.append({'action': a, 'couleur': c})
            else:
                plan.append({'action': a})
        except (KeyError, TypeError, ValueError):
            return Resultat('refus', message="Je n'ai pas compris.")
    return Resultat('plan', plan, message=reponse[:300])


# ── Phrases ──

def _fmt_m(d):
    if d < 1.0:
        return f'{round(d * 100):g} centimètres'
    v = f'{d:.2f}'.rstrip('0').rstrip('.').replace('.', ',')
    return f'{v} mètre' + ('s' if d >= 2 else '')


def decrire(o):
    """dict -> « avancer de 50 centimètres »."""
    a = o['action']
    if a == 'avance':
        return f"avancer de {_fmt_m(o['distance_m'])}"
    if a == 'recule':
        return f"reculer de {_fmt_m(o['distance_m'])}"
    if a == 'crabe':
        return f"me décaler à {o['cote']} de {_fmt_m(o['distance_m'])}"
    if a == 'tourne':
        cote = 'gauche' if o['angle_deg'] > 0 else 'droite'
        return f"tourner à {cote} de {abs(o['angle_deg']):g} degrés"
    if a == 'attrape':
        return f"attraper le cube {o.get('couleur', 'rouge')}"
    if a == 'attrape_tout':
        return 'attraper tous les cubes rouges'
    if a == 'patrouille':
        return 'faire une patrouille'
    if a == 'etat':
        return "donner mon état"
    return a


def decrire_plan(plan):
    return ', puis '.join(decrire(o) for o in plan)


def est_long(plan):
    """Plan à faire confirmer quand il vient de l'IA (tout ce qui bouge)."""
    return any(o['action'] != 'etat' for o in plan)


# ── Consigne donnée à l'IA locale (Ollama) ──

CONSIGNE_IA = """Tu es le module de compréhension d'un petit robot à roues (mecanum) avec un bras.
Tu reçois une phrase en français et tu réponds UNIQUEMENT en JSON :
{"plan": [ ... ], "reponse": "phrase courte en français"}

Actions autorisées dans "plan" (aucune autre) :
- {"action": "avance", "distance_m": nombre}      (0 < distance <= 3)
- {"action": "recule", "distance_m": nombre}      (0 < distance <= 0.4)
- {"action": "crabe", "cote": "gauche"|"droite", "distance_m": nombre}  (<= 1)
- {"action": "tourne", "angle_deg": nombre}       (positif = gauche, négatif = droite, |angle| <= 360)
- {"action": "attrape", "couleur": "rouge"}       (seul le cube rouge est possible)
- {"action": "attrape_tout"}                      (attraper tous les cubes rouges)
- {"action": "patrouille"}
- {"action": "etat"}                              (batterie, sécurité)
5 actions au maximum.

Si la phrase est une question ou une conversation, "plan" est vide et "reponse" contient ta réponse (2 phrases maximum).
Si on demande quelque chose d'impossible avec ces actions, "plan" est vide et "reponse" l'explique.
N'invente jamais d'autre action. Pas de texte hors du JSON."""

SCHEMA_IA = {
    'type': 'object',
    'properties': {
        'plan': {'type': 'array', 'items': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'enum': list(ACTIONS)},
                'distance_m': {'type': 'number'},
                'angle_deg': {'type': 'number'},
                'cote': {'type': 'string', 'enum': ['gauche', 'droite']},
                'couleur': {'type': 'string'},
            },
            'required': ['action'],
        }},
        'reponse': {'type': 'string'},
    },
    'required': ['plan', 'reponse'],
}
