# encoding: utf-8
"""securite_logique.py — logique pure du gardien de sécurité (sans ROS).

Testée hors robot par tests/test_securite_logique.py. Utilisée par
gardien_securite.py, qui ne fait que brancher cette logique sur les topics ROS.

Repère du robot (convention ROS) : x vers l'avant, y vers la gauche,
angles comptés dans le sens inverse des aiguilles d'une montre.
Lidar (mesuré le 10/11) : son angle 180° = avant du robot, sens identique.
Le filtre Hiwonder ne garde que 72°→291° du lidar : vu du robot,
environ -108° → +111°. L'arrière (~140°) est aveugle : montants du robot.
"""
import math
import unicodedata

# ── Réglages par défaut (modifiables par paramètres ROS) ──
DIST_ARRET_M = 0.30        # obstacle plus près (mesuré depuis le lidar) -> arrêt
DIST_RALENTI_M = 0.60      # entre arrêt et ralenti -> vitesse réduite progressivement
DEMI_CONE_DEG = 35.0       # largeur de la zone surveillée de part et d'autre du sens de marche
DIST_MIN_VALIDE_M = 0.12   # en dessous : c'est le robot lui-même, on ignore
LIDAR_DECALAGE_DEG = 180.0 # angle du lidar qui correspond à l'avant du robot
ZONE_AVEUGLE_DEG = 108.0   # |angle robot| au-delà = non couvert par /scan (arrière)
VMAX_LIN = 0.50            # m/s
VMAX_ANG = 2.0             # rad/s
VMAX_RECUL = 0.10          # m/s en marche arrière (zone aveugle)
DUREE_MAX_RECUL_S = 5.0    # recul continu maximal, puis arrêt
FRAIS_S = 0.30             # une commande plus vieille est considérée comme arrêtée

MOTS_ARRET = ['stop', 'arrete', 'arreter', 'arretes', 'arrete toi', 'halte',
              'urgence', 'stoppe', 'pas bouger', 'ne bouge plus']
MOTS_REPRISE = ['reprends', 'reprendre', 'reprise', 'deverrouille', 'deverrouiller',
                'tu peux repartir', 'c est bon repars']


def normaliser(texte):
    """minuscules, sans accents, ponctuation -> espaces."""
    t = unicodedata.normalize('NFD', texte.lower())
    t = ''.join(c for c in t if unicodedata.category(c) != 'Mn')
    t = ''.join(c if c.isalnum() else ' ' for c in t)
    return ' '.join(t.split())


def _contient_mot(texte_norm, expression):
    return f' {expression} ' in f' {texte_norm} '


def est_arret(texte):
    t = normaliser(texte)
    return any(_contient_mot(t, m) for m in MOTS_ARRET)


def est_reprise(texte):
    t = normaliser(texte)
    if est_arret(texte):
        return False
    return any(_contient_mot(t, m) for m in MOTS_REPRISE)


def angle_robot_deg(angle_lidar_rad, decalage_deg=LIDAR_DECALAGE_DEG):
    """Angle d'un point du lidar, exprimé dans le repère du robot, dans [-180, 180)."""
    a = math.degrees(angle_lidar_rad) - decalage_deg
    return (a + 180.0) % 360.0 - 180.0


def ecart_angle_deg(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0)


def distance_dans_cone(angle_min, increment, distances, direction_deg,
                       demi_cone_deg=DEMI_CONE_DEG, dmin=DIST_MIN_VALIDE_M,
                       decalage_deg=LIDAR_DECALAGE_DEG):
    """Distance minimale vue par le lidar dans le cône centré sur direction_deg
    (repère robot). inf si rien de valide."""
    best = math.inf
    for i, r in enumerate(distances):
        if not math.isfinite(r) or r < dmin:
            continue
        a = angle_robot_deg(angle_min + i * increment, decalage_deg)
        if ecart_angle_deg(a, direction_deg) <= demi_cone_deg and r < best:
            best = r
    return best


def facteur_vitesse(distance, arret=DIST_ARRET_M, ralenti=DIST_RALENTI_M):
    """1 = pleine vitesse, 0 = arrêt, linéaire entre les deux seuils."""
    if not math.isfinite(distance) or distance >= ralenti:
        return 1.0
    if distance <= arret:
        return 0.0
    return (distance - arret) / (ralenti - arret)


def borner(v, vmax):
    return max(-vmax, min(vmax, v))


class Gardien:
    """État du gardien. Toutes les méthodes reçoivent l'heure 'maintenant' (s)
    pour être testables sans horloge réelle."""

    def __init__(self, **reglages):
        self.r = dict(
            dist_arret=DIST_ARRET_M, dist_ralenti=DIST_RALENTI_M,
            demi_cone=DEMI_CONE_DEG, dmin=DIST_MIN_VALIDE_M,
            decalage=LIDAR_DECALAGE_DEG, zone_aveugle=ZONE_AVEUGLE_DEG,
            vmax_lin=VMAX_LIN, vmax_ang=VMAX_ANG, vmax_recul=VMAX_RECUL,
            duree_max_recul=DUREE_MAX_RECUL_S, frais=FRAIS_S)
        self.r.update(reglages)
        self.verrou = False          # arrêt général verrouillé
        self.cmd = {'manuel': None, 'auto': None}   # (t, vx, vy, wz)
        self.scan = None             # (t, angle_min, increment, distances)
        self.debut_recul = None
        self.dernier_motif = ''

    # ── entrées ──
    def commande(self, source, t, vx, vy, wz):
        self.cmd[source] = (t, vx, vy, wz)

    def lidar(self, t, angle_min, increment, distances):
        self.scan = (t, angle_min, increment, list(distances))

    def arreter(self):
        """Renvoie True si l'état a changé."""
        changed = not self.verrou
        self.verrou = True
        self.cmd = {'manuel': None, 'auto': None}
        return changed

    def reprendre(self):
        changed = self.verrou
        self.verrou = False
        return changed

    # ── sortie ──
    def calculer(self, t):
        """Renvoie (vx, vy, wz, source, motif). source=None : aucune commande
        active (le nœud publie alors un zéro, puis se tait)."""
        if self.verrou:
            return 0.0, 0.0, 0.0, 'arret', 'arrêt général verrouillé'

        source = None
        for s in ('manuel', 'auto'):          # priorité : manuel > auto
            c = self.cmd[s]
            if c is not None and t - c[0] <= self.r['frais']:
                source = s
                break
        if source is None:
            self.debut_recul = None
            return 0.0, 0.0, 0.0, None, ''

        _, vx, vy, wz = self.cmd[source]
        vx = borner(vx, self.r['vmax_lin'])
        vy = borner(vy, self.r['vmax_lin'])
        wz = borner(wz, self.r['vmax_ang'])
        motif = ''

        vitesse = math.hypot(vx, vy)
        if vitesse > 1e-3:
            direction = math.degrees(math.atan2(vy, vx))
            if abs(direction) > self.r['zone_aveugle']:
                # Marche arrière : le lidar ne voit pas -> lent et limité dans le temps
                if self.debut_recul is None:
                    self.debut_recul = t
                if t - self.debut_recul > self.r['duree_max_recul']:
                    vx = vy = 0.0
                    motif = 'recul trop long (arrière non surveillé)'
                elif vitesse > self.r['vmax_recul']:
                    k = self.r['vmax_recul'] / vitesse
                    vx, vy = vx * k, vy * k
                    motif = 'recul limité (arrière non surveillé)'
            else:
                self.debut_recul = None
                if self.scan is None or t - self.scan[0] > 1.0:
                    vx = vy = 0.0
                    motif = 'lidar muet : déplacement bloqué'
                else:
                    _, amin, inc, dist = self.scan
                    d = distance_dans_cone(amin, inc, dist, direction,
                                           self.r['demi_cone'], self.r['dmin'],
                                           self.r['decalage'])
                    f = facteur_vitesse(d, self.r['dist_arret'], self.r['dist_ralenti'])
                    if f < 1.0:
                        vx, vy = vx * f, vy * f
                        motif = (f'obstacle à {d:.2f} m : arrêt' if f == 0.0
                                 else f'obstacle à {d:.2f} m : ralenti x{f:.2f}')
        else:
            self.debut_recul = None
        self.dernier_motif = motif
        return vx, vy, wz, source, motif
