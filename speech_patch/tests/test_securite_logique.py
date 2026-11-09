# Tests hors robot de la logique du gardien de sécurité.
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import securite_logique as sl  # noqa: E402

INC = math.radians(0.9)


def scan_lidar(obstacles, n=400):
    """Balayage 360° du lidar (angle 0 = arrière du robot). obstacles :
    {angle_robot_deg: distance}. Ailleurs : inf."""
    d = [math.inf] * n
    for ang_robot, dist in obstacles.items():
        ang_lidar = (ang_robot + 180.0) % 360.0
        i = int(round(ang_lidar / 0.9)) % n
        for k in (-2, -1, 0, 1, 2):
            d[(i + k) % n] = dist
    return 0.0, INC, d


def test_normaliser_et_mots():
    assert sl.est_arret('Arrête !')
    assert sl.est_arret('STOP')
    assert sl.est_arret('arrête-toi robot')
    assert not sl.est_arret('avance de un mètre')
    assert not sl.est_arret('stopper')            # mot différent, pas dans la liste
    assert sl.est_reprise('reprends')
    assert sl.est_reprise('Tu peux repartir')
    assert not sl.est_reprise('stop, ne reprends pas')   # l'arrêt l'emporte


def test_orientation_lidar():
    # angle lidar 180° = avant du robot ; lidar -90° (=270°) = gauche (+90° robot)
    assert abs(sl.angle_robot_deg(math.pi)) < 1e-9
    assert abs(sl.angle_robot_deg(math.radians(270)) - 90.0) < 1e-9


def test_priorite_manuel_sur_auto():
    g = sl.Gardien()
    g.lidar(0.0, *scan_lidar({}))
    g.commande('auto', 0.0, 0.2, 0, 0)
    g.commande('manuel', 0.0, 0.1, 0, 0)
    vx, _, _, src, _ = g.calculer(0.1)
    assert src == 'manuel' and abs(vx - 0.1) < 1e-9


def test_commande_perimee():
    g = sl.Gardien()
    g.lidar(1.0, *scan_lidar({}))
    g.commande('auto', 0.0, 0.2, 0, 0)
    vx, _, _, src, _ = g.calculer(1.0)
    assert src is None and vx == 0.0


def test_verrou_bloque_tout_jusqu_a_reprise():
    g = sl.Gardien()
    g.lidar(0.0, *scan_lidar({}))
    assert g.arreter()
    g.commande('manuel', 0.0, 0.3, 0, 0)
    vx, vy, wz, src, _ = g.calculer(0.05)
    assert (vx, vy, wz, src) == (0.0, 0.0, 0.0, 'arret')
    assert g.reprendre()
    g.commande('manuel', 0.1, 0.3, 0, 0)
    vx, _, _, src, _ = g.calculer(0.15)
    assert src == 'manuel' and vx > 0


def test_obstacle_devant_arrete_et_ralentit():
    g = sl.Gardien()
    g.lidar(0.0, *scan_lidar({0: 0.25}))
    g.commande('manuel', 0.0, 0.3, 0, 0)
    vx, _, _, _, motif = g.calculer(0.05)
    assert vx == 0.0 and 'arrêt' in motif
    g.lidar(0.0, *scan_lidar({0: 0.45}))          # à mi-chemin -> x0.5
    vx, _, _, _, _ = g.calculer(0.05)
    assert abs(vx - 0.15) < 1e-6


def test_obstacle_a_cote_ne_gene_pas_l_avance():
    g = sl.Gardien()
    g.lidar(0.0, *scan_lidar({90: 0.20}))          # mur à gauche
    g.commande('manuel', 0.0, 0.3, 0, 0)
    vx, _, _, _, _ = g.calculer(0.05)
    assert abs(vx - 0.3) < 1e-9
    g.commande('manuel', 0.0, 0.0, 0.3, 0)         # crabe vers la gauche -> bloqué
    _, vy, _, _, motif = g.calculer(0.05)
    assert vy == 0.0 and 'obstacle' in motif


def test_rotation_seule_toujours_permise():
    g = sl.Gardien()
    g.lidar(0.0, *scan_lidar({0: 0.15, 90: 0.15}))
    g.commande('auto', 0.0, 0.0, 0.0, 0.8)
    _, _, wz, _, _ = g.calculer(0.05)
    assert abs(wz - 0.8) < 1e-9


def test_recul_limite_en_vitesse_et_en_duree():
    g = sl.Gardien()
    g.lidar(0.0, *scan_lidar({}))
    g.commande('auto', 0.0, -0.3, 0, 0)
    vx, _, _, _, motif = g.calculer(0.05)
    assert abs(vx + 0.10) < 1e-9 and 'recul' in motif
    t = 0.0
    while t < 6.0:                                   # commande renouvelée en continu
        g.commande('auto', t, -0.3, 0, 0)
        g.lidar(t, *scan_lidar({}))
        vx, _, _, _, motif = g.calculer(t)
        t += 0.05
    assert vx == 0.0 and 'trop long' in motif


def test_lidar_muet_bloque_les_deplacements():
    g = sl.Gardien()
    g.commande('manuel', 5.0, 0.3, 0, 0)
    vx, _, _, _, motif = g.calculer(5.0)
    assert vx == 0.0 and 'lidar' in motif


def test_points_du_robot_ignores():
    g = sl.Gardien()
    g.lidar(0.0, *scan_lidar({0: 0.10}))           # < 12 cm : le robot lui-même
    g.commande('manuel', 0.0, 0.3, 0, 0)
    vx, _, _, _, _ = g.calculer(0.05)
    assert abs(vx - 0.3) < 1e-9


def test_vitesses_bornees():
    g = sl.Gardien()
    g.lidar(0.0, *scan_lidar({}))
    g.commande('manuel', 0.0, 2.0, 0, 9.0)
    vx, _, wz, _, _ = g.calculer(0.05)
    assert vx == sl.VMAX_LIN and wz == sl.VMAX_ANG
