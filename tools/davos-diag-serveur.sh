#!/bin/bash
# =============================================================================
# davos-diag-serveur.sh - Diagnostic du serveur Medulla pendant une descente
#                         d'image, et synthese des rapports des postes
#
# Usage :  sudo bash davos-diag-serveur.sh [-d DUREE_S] [-n NB_POSTES] [-I INTERFACE]
#            -d  duree de mesure en secondes (defaut 30)
#            -n  nombre de postes en cours de deploiement (pour detecter les collisions)
#            -I  interface reseau du serveur (defaut : detectee automatiquement)
#
# Resultat : /var/lib/pulse2/imaging/logs/davos-diag/serveur-<date>/rapport.txt
# =============================================================================

DUREE=30; ATTENDU=0; IFACE=""
while getopts "d:n:I:h" o; do
  case $o in d) DUREE=$OPTARG;; n) ATTENDU=$OPTARG;; I) IFACE=$OPTARG;; *) sed -n '2,13p' "$0"; exit 0;; esac
done
[[ $EUID -eq 0 ]] || { echo "A lancer avec sudo."; exit 1; }

IMG_DIR=/var/lib/pulse2/imaging/masters
LOG_DIR=/var/lib/pulse2/imaging/logs
DIAG=$LOG_DIR/davos-diag; [[ -d $LOG_DIR ]] || DIAG=/tmp/davos-diag
OUT=$DIAG/serveur-$(date +%Y%m%d-%H%M%S); mkdir -p "$OUT"; REPORT=$OUT/rapport.txt
NB_OK=0; NB_ATT=0; NB_KO=0; SYN=()
say()  { echo "$*" | tee -a "$REPORT"; }
titre(){ say ""; say "=== $* ==="; }
ok()   { NB_OK=$((NB_OK+1)); say "[OK]        $*"; }
att()  { NB_ATT=$((NB_ATT+1)); say "[ATTENTION] $*"; SYN+=("[ATTENTION] $*"); }
ko()   { NB_KO=$((NB_KO+1)); say "[PROBLEME]  $*"; SYN+=("[PROBLEME]  $*"); }
info() { say "[INFO]      $*"; }

say "Diagnostic serveur Medulla $(hostname) - $(date '+%d/%m/%Y %H:%M:%S')"

# --- Serveur NFS -------------------------------------------------------------
titre "Serveur NFS"
if [[ ! -d /proc/fs/nfsd ]]; then ko "Serveur NFS inactif (/proc/fs/nfsd absent)"; else
  info "Versions : $(cat /proc/fs/nfsd/versions 2>/dev/null)"
  TH=$(cat /proc/fs/nfsd/threads 2>/dev/null); info "Threads nfsd : $TH"
  [[ -n $TH ]] && (( TH < 16 )) && att "Peu de threads nfsd ($TH) : 16 a 32 recommandes pour des deploiements en parallele"
  exportfs -v 2>/dev/null > "$OUT/exportfs.txt"
  EXP=$(grep -A1 "^/var/lib/pulse2/imaging/masters" "$OUT/exportfs.txt" | tr -d '\n\t ' )
  [[ -n $EXP ]] && info "Export des images : $EXP" || att "Export des images non trouve dans exportfs -v"
fi

# --- Clients NFS -------------------------------------------------------------
titre "Clients NFS"
GENERIC_RE='^Linux NFSv4\.[0-9]+ (debian|ubuntu|localhost|localhost\.localdomain|clonezilla|\(none\))?$'
V4=$(for f in /proc/fs/nfsd/clients/*/info; do [[ -f $f ]] || continue
  a=$(awk -F'"' '/^address:/{split($2,x,":"); print x[1]}' "$f"); n=$(awk -F'"' '/^name:/{print $2}' "$f"); echo "$a|$n"; done | sort -u)
TCP=$(ss -tnH state established '( sport = :2049 )' 2>/dev/null | awk '{print $4}' | sed 's/:[0-9]*$//;s/^\[//;s/\]$//;s/^::ffff://' | sort -u)
NB_V4=$( [[ -n $V4 ]] && wc -l <<<"$V4" || echo 0 ); NB_TCP=$( [[ -n $TCP ]] && wc -l <<<"$TCP" || echo 0 )
info "Machines connectees en TCP au port 2049 : $NB_TCP - clients NFSv4 enregistres : $NB_V4"
if [[ -n $V4 ]]; then
  echo "$V4" | awk -F'|' -v re="$GENERIC_RE" '{
    if ($2 ~ /davos-/) t="[OK] identite unique"; else if ($2 ~ re) t="[PROBLEME] nom generique (correctif absent)"; else t="autre machine";
    printf "              %-16s %-45s %s\n", $1, $2, t}' | tee -a "$REPORT"
  GEN=$(cut -d'|' -f2 <<<"$V4" | grep -E "$GENERIC_RE" | grep -v davos- | sort -u | sed 's/Linux NFSv4.[0-9]* //' | paste -sd, -)
  DUP=$(cut -d'|' -f2 <<<"$V4" | sort | uniq -d)
  [[ -n $GEN ]] && ko "Postes DavOS avec un nom NFSv4 generique ($GEN) : collision entre postes"
  [[ -n $DUP ]] && ko "Plusieurs adresses partagent la meme identite NFSv4"
  [[ -z $GEN && -z $DUP ]] && ok "Identites NFSv4 uniques"
fi
(( NB_TCP > NB_V4 )) && info "$((NB_TCP-NB_V4)) machine(s) connectee(s) sans identite NFSv4 propre (NFSv3, ou collision)"
(( ATTENDU > 0 && NB_TCP < ATTENDU )) && att "Moins de machines connectees ($NB_TCP) que de postes annonces ($ATTENDU)"

# --- Reseau et stockage : mesures --------------------------------------------
titre "Mesures pendant ${DUREE} s"
[[ -z $IFACE ]] && IFACE=$(ip route | awk '/^default/{print $5; exit}')
SPEED=$(cat /sys/class/net/$IFACE/speed 2>/dev/null)
info "Interface : $IFACE - $( [[ ${SPEED:-0} -gt 0 ]] && echo "$SPEED Mbit/s" || echo "vitesse non exposee (VM virtio)")"
ERRS=$(ethtool -S "$IFACE" 2>/dev/null | grep -iE 'err|drop|miss' | awk -F: '$2+0>0{gsub(/^ +/,"",$1); printf "%s=%d ", $1, $2}')
[[ -n $ERRS ]] && att "Compteurs d'erreurs non nuls sur $IFACE : $ERRS"
SRC=$(findmnt -no SOURCE -T "$IMG_DIR" 2>/dev/null); DEV=$(lsblk -no PKNAME "$SRC" 2>/dev/null | head -1); [[ -z $DEV ]] && DEV=$(basename "$SRC")
info "Stockage des images : $SRC (disque $DEV) - $(df -h --output=avail "$IMG_DIR" 2>/dev/null | tail -1 | xargs) libres"
txb() { cat /sys/class/net/$IFACE/statistics/tx_bytes; }
rdsec() { awk -v d="$DEV" '$3==d{print $6}' /proc/diskstats; }
cpu() { awk '/^cpu /{print $2+$3+$4+$7+$8+$9, $5, $6}' /proc/stat; }
pool() { awk 'NR>1 && $1 ~ /^[0-9]+$/ {p+=$2; s+=$3} END{print p+0, s+0}' /proc/fs/nfsd/pool_stats 2>/dev/null; }
T0=$(txb); D0=$(rdsec); read -r B0 I0 W0 <<<"$(cpu)"; read -r P0 S0 <<<"$(pool)"
for ((t=5; t<=DUREE; t+=5)); do
  sleep 5; T1=$(txb); D1=$(rdsec); read -r B1 I1 W1 <<<"$(cpu)"
  dt=$(( (B1-B0)+(I1-I0)+(W1-W0) )); (( dt==0 )) && dt=1
  MB=$(( (T1-T0)*8/5/1000000 )); RD=$(( (${D1:-0}-${D0:-0})*512/5/1000000 ))
  printf "  %s  emis %6s Mbit/s | lecture disque %5s Mo/s | CPU %3s%% (iowait %2s%%)\n" "$(date +%H:%M:%S)" "$MB" "$RD" "$(( (B1-B0)*100/dt ))" "$(( (W1-W0)*100/dt ))" | tee -a "$REPORT"
  S_MB=$((S_MB+MB)); S_RD=$((S_RD+RD)); S_W=$((S_W+(W1-W0)*100/dt)); N=$((N+1))
  T0=$T1; D0=$D1; B0=$B1; I0=$I1; W0=$W1
done
read -r P1 S1 <<<"$(pool)"; (( N==0 )) && N=1
A_MB=$((S_MB/N)); A_W=$((S_W/N))
info "Moyennes : emis ${A_MB} Mbit/s, lecture disque $((S_RD/N)) Mo/s, iowait ${A_W}%"
(( A_W >= 20 )) && att "Attente disque elevee sur le serveur (iowait ${A_W}%)"
if (( P1 > P0 )); then
  Q=$(( (S1-S0)*100/(P1-P0) ))
  (( Q >= 10 )) && att "${Q}% des requetes NFS ont attendu un thread nfsd libre : augmenter le nombre de threads" || ok "Threads nfsd suffisants (${Q}% de requetes en attente)"
fi
if (( NB_TCP > 0 )); then
  PAR=$((A_MB/NB_TCP)); info "Debit moyen par machine connectee : ~${PAR} Mbit/s"
  (( PAR < 300 )) && att "Debit par poste faible (~${PAR} Mbit/s) : lancer davos-diag.sh sur un poste pour localiser le goulot"
fi

# --- Rapports des postes -----------------------------------------------------
titre "Rapports des postes (davos-diag.sh)"
if ls "$DIAG"/*/rapport.txt >/dev/null 2>&1; then
  printf "  %-22s %-19s %-10s %-12s %-6s %s\n" "Poste" "Date" "Lien" "Reseau moy." "Prob." "Premier probleme" | tee -a "$REPORT"
  for r in $(ls -t "$DIAG"/*/rapport.txt | grep -v '/serveur-'); do
    h=$(basename "$(dirname "$r")"); host=${h%-*-*}; [[ " $SEEN " == *" $host "* ]] && continue; SEEN="$SEEN $host"
    d=$(sed -n 's/.* - \([0-9/]* [0-9:]*\)$/\1/p' "$r" | head -1)
    l=$(grep -oE 'Lien (negocie )?a [0-9]+ Mbit/s' "$r" | grep -oE '[0-9]+' | head -1)
    m=$(grep -oE 'Moyennes : reseau [0-9]+' "$r" | grep -oE '[0-9]+$')
    k=$(grep -c '^\[PROBLEME\]' "$r"); p=$(grep -m1 '^\[PROBLEME\]' "$r" | sed 's/^\[PROBLEME\] *//' | cut -c1-70)
    printf "  %-22s %-19s %-10s %-12s %-6s %s\n" "$host" "$d" "${l:-?} Mb/s" "${m:-?} Mb/s" "$k" "${p:--}" | tee -a "$REPORT"
  done
else info "Aucun rapport de poste dans $DIAG (lancer davos-diag.sh sur les postes)"; fi

# --- Logs DavOS envoyes par les postes ---------------------------------------
titre "Logs de restauration des postes (debug_imaging)"
if [[ -d $LOG_DIR/debug_imaging ]]; then
  for d in "$LOG_DIR"/debug_imaging/*/; do
    f=$(ls -t "$d"davos_restorer-*.log 2>/dev/null | head -1); [[ -z $f ]] && continue
    e=$(grep -ciE 'error|fail|abort|no space' "$f"); r=$(grep -oE 'Ave\. Rate: *[0-9.]+ *[GM]B/min' "$f" | tail -1 | sed 's/Ave. Rate: *//')
    printf "  %-22s %-38s erreurs : %-4s debit partclone : %s\n" "$(basename "$d")" "$(basename "$f")" "$e" "${r:--}" | tee -a "$REPORT"
  done
else info "Pas de dossier $LOG_DIR/debug_imaging"; fi

# --- Synthese ----------------------------------------------------------------
{ echo ""; echo "=== Synthese ==="; echo "$NB_OK OK, $NB_ATT attention(s), $NB_KO probleme(s)"
  for l in "${SYN[@]}"; do echo "  $l"; done; echo ""; echo "Rapport : $REPORT"; } | tee -a "$REPORT"
