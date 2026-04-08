#!/bin/bash
# XP-Arc Hourly Batch Runner
# Runs 6 batches of 1000 entities every 10 minutes within a single hourly execution

cd /home/user/workspace/xp-arc

LOG=/home/user/workspace/xp-arc/batch_log.txt

log() { echo "[$(date -u +%H:%M:%S)] $1" | tee -a "$LOG"; }

log "═══ HOURLY SESSION START ═══"
TOTAL_START=$(date +%s)

for i in 1 2 3 4 5 6; do
    # Check remaining raw
    RAW=$(python3 -c "
import sqlite3
try:
    c = sqlite3.connect('dragon_hoard.db')
    r = c.execute(\"SELECT COUNT(*) FROM entities WHERE status='raw'\").fetchone()[0]
    comp = c.execute(\"SELECT COUNT(*) FROM entities WHERE status='completed'\").fetchone()[0]
    print(f'{r},{comp}')
    c.close()
except:
    print('0,0')
")
    RAW_COUNT=$(echo $RAW | cut -d',' -f1)
    COMP_COUNT=$(echo $RAW | cut -d',' -f2)
    
    log "Batch $i/6 | Raw: $RAW_COUNT | Completed: $COMP_COUNT"
    
    if [ "$RAW_COUNT" -eq 0 ]; then
        log "Hoard fully processed! All entities complete."
        break
    fi
    
    # Run batch with 480s timeout
    timeout 480 python3 batch_run.py --batch-size 1000
    STATUS=$?
    
    if [ $STATUS -ne 0 ]; then
        log "Batch $i exited with status $STATUS"
    fi
    
    # Wait 10 minutes before next batch (except after last one)
    if [ $i -lt 6 ] && [ "$RAW_COUNT" -gt 1000 ]; then
        log "Waiting 10 minutes before next batch..."
        sleep 600
    fi
done

TOTAL_END=$(date +%s)
ELAPSED=$((TOTAL_END - TOTAL_START))
log "═══ HOURLY SESSION COMPLETE — ${ELAPSED}s total ═══"
