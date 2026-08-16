from datetime import date
from fact_store import InMemoryFactStore
from weekly_mystery import mystery_for_key, is_correct_guess
from fact_engine import daily_facts_for_date

checks=[]
def check(name, cond):
    checks.append((name,bool(cond)))
    print(('PASS' if cond else 'FAIL')+': '+name)

# Typo tolerance: plausible spelling errors pass; unrelated/short answers stay strict.
lincoln=mystery_for_key('abraham-lincoln')
check('exact mystery answer', is_correct_guess(lincoln,'Abraham Lincoln'))
check('missing letter accepted', is_correct_guess(lincoln,'Abraham Lincon'))
check('adjacent transposition accepted', is_correct_guess(lincoln,'Abraham Linclon'))
check('small spelling error accepted', is_correct_guess(lincoln,'Abraham Linkoln'))
check('alias still accepted', is_correct_guess(lincoln,'Abe Lincoln'))
check('different person rejected', not is_correct_guess(lincoln,'George Lincoln'))
mars=mystery_for_key('mars')
check('short answer remains strict', not is_correct_guess(mars,'Mers'))

# Test student is real persistence, but hidden from classroom lists/stats.
store=InMemoryFactStore()
cls=store.create_class('Block 2')
real=store.create_student(cls.class_id,'FalconFox','1234')
test=store.reset_test_student(cls.class_id)
check('test student flagged', test.is_test)
check('test student hidden from roster', [s.nickname for s in store.list_students(cls.class_id)] == ['FalconFox'])
check('test student retrievable directly', store.get_test_student(cls.class_id).student_id == test.student_id)

week=date(2026,8,10)
store.get_or_create_weekly_mystery(week,'abraham-lincoln')
challenge=store.get_or_create_challenge(date(2026,8,13),'TDFC-DAILY-v1',daily_facts_for_date(date(2026,8,13)))
store.unlock_mystery_day(test.student_id,week,4,challenge.challenge_id)
check('test unlock does not lock real mystery', not store.weekly_mystery_locked(week))
store.submit_mystery_guess(test.student_id,week,'Abraham Lincon',correct=True,clue_count=1,guess_day=4)
check('test solve excluded from teacher mystery stats', store.weekly_mystery_teacher_stats(week)['correct']==0)
check('test solve excluded from raffle', store.weekly_mystery_correct_students(week)==[])

# Real correct solver gets one unique raffle entry even if implementation ever sees multiple guesses.
store.unlock_mystery_day(real.student_id,week,4,challenge.challenge_id)
store.submit_mystery_guess(real.student_id,week,'Abraham Lincoln',correct=True,clue_count=4,guess_day=4)
eligible=store.weekly_mystery_correct_students(week)
check('real solver eligible', len(eligible)==1 and eligible[0]['student_id']==real.student_id)
check('real solver locks mystery', store.weekly_mystery_locked(week))

# Reset destroys old sandbox data and recreates a fresh hidden account.
old_id=test.student_id
fresh=store.reset_test_student(cls.class_id)
check('sandbox reset creates new id', fresh.student_id != old_id)
check('fresh sandbox still hidden', all(not s.is_test for s in store.list_students(cls.class_id)))

# App setting can persist raffle winner/reference state.
store.set_app_setting('weekly_mystery_raffle::2026-08-10', {'student_id': real.student_id})
check('raffle setting persists', store.get_app_setting('weekly_mystery_raffle::2026-08-10')['student_id']==real.student_id)

failed=[name for name,ok in checks if not ok]
if failed:
    raise SystemExit(f'Failed {len(failed)} checks: {failed}')
print(f'v2.9 raffle/typo/test-student regression: {len(checks)}/{len(checks)} checks passed')
