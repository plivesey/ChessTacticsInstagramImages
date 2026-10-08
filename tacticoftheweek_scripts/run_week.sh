cd ~/chess-tactics/tacticoftheweek
LABEL=${1:-test}
rm -f week_done week_log.txt
echo "fetching games" > week_status.txt
rm -rf games/lichess games/twic games/online games/picked_wi week_run
mkdir -p games/lichess games/twic games/online games/picked_wi
curl -s -m 120 "https://lichess.org/api/broadcast?nb=200" -o /tmp/lichess_bc.ndjson
N=$(curl -s -m 30 "https://theweekinchess.com/twic" | grep -o "zips/twic[0-9]*g.zip" | grep -o "[0-9][0-9][0-9][0-9]" | sort -u | tail -1)
if [ -n "$N" ]; then
  sed -i "s/twic[0-9]*g/twic${N}g/g" fetch_games.sh unzip_twic.py
fi
sh fetch_games.sh >> week_log.txt 2>&1
echo "fetching online games" > week_status.txt
python3 fetch_online.py >> week_log.txt 2>&1
echo "ranking games" > week_status.txt
curl -s -m 60 "https://ratings.fide.com/a_top.php?list=men" -o /tmp/fide_men.html
if ! grep -q Carlsen /tmp/fide_men.html; then
  curl -s -m 60 -A "Mozilla/5.0" "https://ratings.fide.com/a_top.php?list=men" -o /tmp/fide_men.html
fi
python3 rank_winner_inc.py > picks_wi_full.txt 2>&1
echo "analyzing games and building the video" > week_status.txt
python3 scan_and_build.py --date "$LABEL" >> week_log.txt 2>&1
echo "finished" > week_status.txt
echo DONE > week_done
