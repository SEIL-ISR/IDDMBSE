# One trial is a headless Isaac Sim process: a few seconds of stage open, a few
# of physics initialisation and the first step, then the drive itself. TIMEOUT_SEC
# stays under the 300 s the RQ job carries so the experiment ends the trial
# itself rather than the queue killing the job; sim_trial.py is given 20 s less
# again, so the simulator is the first thing to go.
PAUSE_BEFORE_READY_SEC = 1
TIMEOUT_SEC = 260
RUN_CHECK_READY_PERIOD_SEC = 1.0
CALLBACKS_LOOP_CHECK_COMPLETE_PERIOD_SEC = 2.0
