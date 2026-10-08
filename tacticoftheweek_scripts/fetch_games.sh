cd ~/chess-tactics/tacticoftheweek
rm -f fetch.done fetch_log.txt
python3 list_round_ids.py > round_ids.txt
for id in $(cat round_ids.txt); do
  out=games/lichess/$id.pgn
  if [ -s "$out" ]; then continue; fi
  code=$(curl -s -m 60 -o "$out" -w "%{http_code}" "https://lichess.org/api/broadcast/round/$id.pgn")
  if [ "$code" = "429" ]; then
    sleep 65
    code=$(curl -s -m 60 -o "$out" -w "%{http_code}" "https://lichess.org/api/broadcast/round/$id.pgn")
  fi
  echo "$id $code" >> fetch_log.txt
  sleep 1
done
curl -s -m 180 -o games/twic/twic1665g.zip https://theweekinchess.com/zips/twic1665g.zip
python3 unzip_twic.py >> fetch_log.txt 2>&1
python3 list_candidates.py > candidates.txt 2>&1
echo DONE > fetch.done
