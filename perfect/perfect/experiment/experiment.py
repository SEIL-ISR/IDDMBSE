import abc
import asyncio
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import time
import traceback
from enum import Flag, auto
from itertools import chain
from typing import Any, Callable, Optional

import yaml

import perfect.logging

logger = perfect.logging.getLogger("core")


class TrialState(Flag):
    INSTANTIATED = auto()
    INITIALIZING = auto()
    INITIALIZED = auto()
    READY = auto()
    STARTING = auto()
    RUNNING = auto()
    CANCELLED = auto()
    ERRORED = auto()
    SUCCESSFUL = auto()
    TIMED_OUT = auto()
    COMPLETE = CANCELLED | ERRORED | SUCCESSFUL | TIMED_OUT
    SHUTTING_DOWN = auto()
    SHUT_DOWN = auto()


class BaseExperiment(abc.ABC):
    _files: dict[str, Optional[str|os.PathLike]]

    def __init__(
        self,
        design,
        environment,
        config,
        trial_id: Optional[int] = None,
        relay_update_callback: Optional[Callable[[str, Any, int], None]] = None,
        stopping_callback: Optional[Callable[[int], bool]] = None,
        **kwargs,
    ):
        self.__id = trial_id
        self.__design = design
        self.__environment = environment
        self.__state = TrialState.INSTANTIATED
        self.__relay_update_callback = relay_update_callback
        self.__stopping_callback = stopping_callback
        self.__inst_time = time.time()
        self.__name = self.__class__.__name__
        if self.__id:
            self.__name += f"_{self.__id}"
        self._config = config
        self._records_root = None
        if config["RECORDS_ENABLED"]:
            self._records_root = os.path.join(config["RECORDS_ROOT"], f"trial_{trial_id}")
            os.makedirs(self._records_root, exist_ok=True)
            self._initialize_records()

        self._working_files = {}
        self._create_working_files()
        edit_working_files(self._working_files, *design, environment)

    def __str__(self):
        return self.name

    def _create_working_files(self):
        self.__temp_dir = tempfile.TemporaryDirectory()
        logger.debug(f"Creating working files in {self.__temp_dir.name}")
        for filepath_alias, default_filepath in self._files.items():
            temp_path = os.path.join(self.__temp_dir.name, filepath_alias)
            if default_filepath:
                self._working_files[filepath_alias] = shutil.copy2(default_filepath, temp_path)
            else:
                self._working_files[filepath_alias] = pathlib.Path(os.path.join(self.__temp_dir.name, filepath_alias))
                self._working_files[filepath_alias].touch()

    def _initialize_records(self):
        with open(os.path.join(self._records_root, "config.json"), "w") as f:
            json.dump(self._config, f, indent=2)
        with open(os.path.join(self._records_root, "design.json"), "w") as f:
            json.dump(self.__design, f, indent=2)
        with open(os.path.join(self._records_root, "environment.json"), "w") as f:
            json.dump(self.__environment, f, indent=2)
        with open(os.path.join(self._records_root, "git.log"), "w") as f:
            git_log_p = subprocess.Popen("git log -n 1".split(), stdout=f)
            git_log_p.wait()
        with open(os.path.join(self._records_root, "pip_list"), "w") as f:
            pip_list_p = subprocess.Popen("pip list".split(), stdout=f)
            pip_list_p.wait()

    async def _relay_update(self, update, data):
        # Users may add whatever customization they want to Experiment updates,
        #  but they shouldn't be allowed to change what the Runner gives
        #  Experiments to do.
        await self.__relay_update_callback(update, data, self.__id)

    async def __set_state(
        self,
        set_: Optional[TrialState] = None,
        unset: Optional[TrialState] = None,
    ):
        if set_:
            self.__state |= set_
        if unset:
            self.__state &= ~unset
        await self._relay_update("state", self.__state.value)

    @property
    def id(self) -> int:
        return self.__id

    @property
    def state(self) -> TrialState:
        return self.__state

    def get_design(self):
        return self.__design

    def get_environment(self):
        return self.__environment

    @property
    def name(self):
        return self.__name

    @abc.abstractmethod
    def _init(self):
        pass

    @abc.abstractmethod
    def _check_if_ready(self) -> bool:
        pass

    @abc.abstractmethod
    async def _run(self):
        pass

    @abc.abstractmethod
    def _check_if_cancelled(self) -> bool:
        pass

    @abc.abstractmethod
    def _check_if_errored(self) -> bool:
        pass

    @abc.abstractmethod
    def _check_if_successful(self) -> bool:
        pass

    @abc.abstractmethod
    def _check_if_timed_out(self) -> bool:
        pass

    @abc.abstractmethod
    def _shut_down(self):
        pass

    async def __init(self):
        await self.__set_state(
            TrialState.INITIALIZING, unset=TrialState.INSTANTIATED
        )
        self._init()
        await self.__set_state(
            TrialState.INITIALIZED, unset=TrialState.INITIALIZING
        )
        self.__init_time = time.time()

    async def __check_if_ready(self) -> bool:
        if self._check_if_ready():
            await self.__set_state(
                TrialState.READY, unset=TrialState.INITIALIZED
            )
        return self.is_ready

    async def __run(self):
        self.__start_time = time.time()
        await self.__set_state(TrialState.RUNNING, unset=TrialState.READY)
        await self._run()

    async def __check_if_stopping(self):
        if self.__stopping_callback is not None:
            return await self.__stopping_callback(trial_id=self.__id)
        return False

    async def __check_stopwatch(self):
        try:
            await self._relay_update("init_age", self.init_age)
            await self._relay_update("start_age", self.start_age)
        except AttributeError:
            pass

    async def __check_for_completion(self) -> bool:
        logger.debug("Checking for completion...")
        if self._check_if_errored():
            await self.__set_state(TrialState.ERRORED)
        elif await self.__check_if_stopping() or self._check_if_cancelled():
            await self.__set_state(TrialState.CANCELLED)
        elif self._check_if_timed_out():
            await self.__set_state(TrialState.TIMED_OUT)
        elif self._check_if_successful():
            await self.__set_state(TrialState.SUCCESSFUL)
        if self.__state & TrialState.COMPLETE:
            await self.__set_state(unset=TrialState.RUNNING)
        logger.debug(f"{self.is_complete=} {self.__state=}")
        return self.is_complete

    async def __shut_down(self):
        # READY and RUNNING _should_ be unset already
        await self.__set_state(
            TrialState.SHUTTING_DOWN, unset=TrialState.RUNNING
        )
        self._shut_down()
        await self.__set_state(
            TrialState.SHUT_DOWN, unset=TrialState.SHUTTING_DOWN
        )
        logger.debug(f"Cleaning up temporary directory {self.__temp_dir.name}")
        self.__temp_dir.cleanup()

    @property
    def is_ready(self) -> bool:
        return bool(TrialState.READY & self.__state)

    @property
    def is_running(self) -> bool:
        return bool(TrialState.RUNNING & self.__state)

    @property
    def is_complete(self) -> bool:
        return bool(TrialState.COMPLETE & self.__state)

    @property
    def init_age(self):
        try:
            return time.time() - self.__init_time
        except AttributeError:
            logger.debug(f"{self.__class__.__name__}.init_age was called, but {self} is not initialized")
            raise

    @property
    def start_age(self):
        try:
            return time.time() - self.__start_time
        except AttributeError:
            logger.debug(f"{self.__class__.__name__}.start_age was called, but {self} is not started")
            raise

    async def __callbacks_loop(self):
        while not self.is_running:
            logger.debug(f"Waiting for {self} to start")
            await asyncio.sleep(self._config["CALLBACKS_LOOP_CHECK_READY_PERIOD_SEC"])
            await self.__check_stopwatch()
        logger.debug("Entering checks loop")
        while (
            self.is_running and not await self.__check_for_completion()
        ):  # e.g., stopped, timed out, successful
            logger.debug(f"Waiting for {self} to complete")
            await asyncio.sleep(self._config["CALLBACKS_LOOP_CHECK_COMPLETE_PERIOD_SEC"])
            await self.__check_stopwatch()
        else:
            logger.info("Exiting checks loop")

    async def run(self):
        try:
            logger.info(f"Initializing {self}")
            await self.__init()
            logger.info(f"Initialized {self}")
            while not await self.__check_if_ready():
                logger.debug(f"Waiting for {self} to be ready")
                await asyncio.sleep(self._config["RUN_CHECK_READY_PERIOD_SEC"])
                await self.__check_stopwatch()
            else:
                logger.info(f"Ready to start {self}")
            logger.info(f"Starting {self}")
            callbacks_task = asyncio.create_task(self.__callbacks_loop())
            run_task = asyncio.create_task(self.__run())
            await run_task
            await callbacks_task
        except Exception as e:
            await self.__set_state(TrialState.ERRORED)
            logger.error(f"Caught exception in run:\n{traceback.format_exc()}")
        finally:
            logger.info(f"Shutting down {self}")
            await self.__shut_down()
            logger.info(f"Shut down {self}")

    @classmethod
    async def launch_async(cls, loop, **kwargs):
        exp = cls(**kwargs)
        await exp.run()

    @classmethod
    def launch(cls, **kwargs):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(cls.launch_async(loop, **kwargs))


def extract_kv_pairs(t, k, v, *dicts):
    for d in dicts:
        try:
            for kv in d.get(t, []):
                yield kv[k], kv[v]
        except AttributeError as e:
            logger.error(f"Encountered {kv} when extracting {k=}: {v=} from {t}")


def edit_working_files(filepath_mappings, *implementations):
    for impl in chain(implementations):
        for file in impl.get("files", []):
            filepath = filepath_mappings[file["file"]]
            if filepath.endswith(".yaml"):
                edit_local_yaml(filepath, file["updates"])
            elif filepath.endswith(".usd"):
                edit_local_usd(filepath, file["updates"])
            else:
                raise NotImplementedError


def edit_local_yaml(filepath, updates):
    contents = yaml.safe_load(open(filepath, "r"))
    for update in updates:
        to_update = contents
        keys = update["keys"].split(".")
        for key in keys[:-1]:
            to_update = to_update[key]
        if isinstance(to_update[keys[-1]], list):
            if isinstance(update["value"], list):
                to_update[keys[-1]].extend(update["value"])
            else:
                to_update[keys[-1]].append(update["value"])
        else:
            to_update[keys[-1]] = update["value"]
    with open(filepath, "w") as f:
        yaml.dump(contents, f)


def edit_local_usd(filepath, updates):
    from pxr import Usd  # only needed for .usd files, and only Isaac Sim's Python has it
    stage = Usd.Stage.Open(filepath, Usd.Stage.LoadNone)
    for update in updates:
        prim = stage.GetPrimAtPath(update["prim"])
        attribute = prim.GetAttribute(update["attribute"])
        attribute.Set(update["value"])
    directory = os.path.dirname(filepath)
    stage.Export(f"{directory}/Nova_Carter_ROS_working.usd")


async def mock_relay_update_callback(update, data, trial_id):
    logger.info(f"Experiment {trial_id} update {update} to {repr(data)}")


async def mock_stopping_callback(trial_id):
    return False
