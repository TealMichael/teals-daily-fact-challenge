from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPT = (ROOT / "AWTRIX_FactTop10.berry").read_text(encoding="utf-8")
MELODY = '"soundRtttl":"top10:d=8,o=6,b=150:c,e,g"'

def check(condition, message):
    if not condition:
        raise AssertionError(message)
    print("PASS:", message)

check("# @version 1.1" in SCRIPT, "Fact Top 10 Berry script version bumped to 1.1")
check(SCRIPT.count(MELODY) == 2, "Top 10 melody is attached to exactly manual and automatic notifications")
check('notify({"text":str(manual_text), "repeat":2, "stack":true, ' + MELODY + '})' in SCRIPT,
      "manual Send Top 10 notification gets the one-time chime")
check('notify({"text":str(auto_text), "repeat":2, "stack":true, ' + MELODY + '})' in SCRIPT,
      "automatic block Top 10 notification gets the one-time chime")
check("soundLoop" not in SCRIPT, "Top 10 chime is not configured to loop")
check("Class Schedule" not in SCRIPT, "Fact Top 10 script stays independent of the Class Schedule app")
print("v2_12_0_awtrix_top10_chime_tests: PASS (6 checks)")
