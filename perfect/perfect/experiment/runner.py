import asyncio
import functools
import json
import signal

import websockets
from websockets.server import WebSocketServerProtocol

import perfect.logging
from perfect.experiment.experiment import BaseExperiment

logger = perfect.logging.getLogger("runner")


class Runner:
    def __init__(self, experiment_cls: type[BaseExperiment]):
        self._cancel = None
        self._experiment_cls = experiment_cls
        self._exp = None
        self._running = False

    def _exit(self, signame, loop):
        logger.info("got signal %s" % signame)
        if not self._restart_f.done():
            self._restart_f.set_result(False)

    @staticmethod
    async def _respond(websocket_, success: bool, comment: str, **data) -> str:
        await websocket_.send(
            json.dumps(
                dict(
                    success=success,
                    comment=comment,
                    data=data,
                )
            )
        )

    async def _handle_msg(self, msg, websocket_: WebSocketServerProtocol):
        op = msg.get("op")
        if op == "launch":
            if self._running:
                await self._respond(
                    websocket_, False, "Already running an experiment"
                )
            else:
                await self._respond(
                    websocket_, True, f"Launching {self._experiment_cls.__name__}"
                )
                self._running = True
                await self._launch_experiment(msg, websocket_)
        elif op == "info":
            await self._respond(
                websocket_,
                True,
                "Details of this Runner",
                class_name=self.__class__.__name__,
                id=str(websocket_.id),
                local_address=websocket_.local_address,
                remote_address=websocket_.remote_address,
                open=websocket_.open,
                closed=websocket_.closed,
                close_code=websocket_.close_code,
                close_reason=websocket_.close_reason,
                is_running=self._running,
                is_cancelled=self._cancel,
            )
        elif op == "cancel":
            if self._cancel is None:
                await self._respond(
                    websocket_,
                    False,
                    "No experiment to cancel",
                    cancelled=self._cancel,
                )
            elif self._cancel:
                await self._respond(
                    websocket_,
                    False,
                    "Experiment is already cancelled",
                    cancelled=self._cancel,
                )
            else:
                self._cancel = True
                await self._respond(
                    websocket_,
                    True,
                    "Cancelling experiment",
                    cancelled=self._cancel,
                )
        elif op == "close":
            self._restart_f.set_result(False)
        elif op == "restart":
            self._restart_f.set_result(True)
        elif op == "get_last_msg":
            if self._exp is not None:
                topic = msg["info"]["topic"]
                await self._respond(
                    websocket_,
                    True,
                    f"{topic} = {self._exp.get_last_msg(topic)}",
                )
            else:
                await self._respond(
                    websocket_,
                    False,
                    "No experiment running",
                )
        elif op == "create_subscription":
            if self._exp is not None:
                topic = msg["info"]["topic"]
                msg_type = msg["info"]["msg_type"]
                try:
                    self._exp.create_subscription(topic, msg_type)
                except Exception as e:
                    await self._respond(
                        websocket_,
                        False,
                        f"Failed to subscribe to {topic}: '{e}'",
                    )
                else:
                    await self._respond(
                        websocket_,
                        True,
                        f"Subscribed to {topic}",
                    )
            else:
                await self._respond(
                    websocket_,
                    False,
                    "No experiment running",
                )
        else:
            await websocket_.send(
                json.dumps(f"What the junk is that? Got unknown op {op}")
            )

    async def _stopping_callback(self, trial_id):
        # TODO this might be unnecessary if we have the Runner keep a reference to the experiment
        return self._cancel

    async def _relay_update_callback(self, update, data, trial_id, websocket_):
        await websocket_.send(
            json.dumps(
                {
                    "update": update,
                    "trial_id": trial_id,
                    "data": data,
                }
            )
        )

    def _set_exp(self, exp: BaseExperiment):
        self._exp = exp

    async def _launch_experiment(self, msg, websocket_):
        self._cancel = False
        await self._experiment_cls.launch_async(
            loop=asyncio.get_running_loop(),
            exp_callback=self._set_exp,
            **msg["info"],  # This should contain design, environment, and config
            relay_update_callback=functools.partial(
                self._relay_update_callback, websocket_=websocket_
            ),
            stopping_callback=self._stopping_callback,
        )
        await websocket_.send(json.dumps(dict(result=dict(cancelled=self._cancel))))
        self._cancel = None
        self._running = False

    async def _handler(self, websocket_):
        msg = await websocket_.recv()
        msg = json.loads(msg)
        try:
            await self._handle_msg(msg, websocket_)
        except websockets.exceptions.WebSocketException as e:
            logger.info(
                f"Oops, tried to handle a message {msg} and got '{e}'. Did the client shutdown?"
            )

    async def _run_websocket(self):
        loop = asyncio.get_running_loop()
        for signame in {"SIGINT", "SIGTERM"}:
            loop.add_signal_handler(
                getattr(signal, signame),
                functools.partial(self._exit, signame, loop),
            )

        self._restart_f = loop.create_future()
        while not self._restart_f.done() or self._restart_f.result():
            if self._restart_f.done():
                self._restart_f = loop.create_future()
            port = 8003  # TODO get from configuration
            logger.info(f"Starting server on port {port}")
            server = await websockets.serve(self._handler, "", port)
            logger.info("Started server and awaiting stop")
            await self._restart_f
            logger.debug(f"{self._restart_f=}")
            logger.info("Closing server")
            server.close()
        logger.info("Closed server")

    async def run(self):
        ws_task = asyncio.create_task(self._run_websocket())
        await ws_task


def main(experiment="experiment"):
    experiment = __import__(experiment)
    r = Runner(experiment.Experiment)
    asyncio.run(r.run())
    logger.info("exit main")


if __name__ == "__main__":
    import sys

    main("experiment" if len(sys.argv) < 2 else sys.argv[1])
