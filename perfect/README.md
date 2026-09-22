# PERFECT

## Description

The PERFormance Evaluation Composible Toolsuite (PERFECT) project is for design space exploration for and simulated testing of systems implemented with the Robot Operating System (ROS). System definitions (for example, of a UGV) are broken into cohesive, decoupled "components" such as sensors, planners, and controllers. A "design" consists of a subset of components sufficient for defining an instance of a general design that may be tested and evaluated. Simulated environments and operation plans (i.e., instructions and scenarios) are also represented as a subset of cohesive, decoupled components.

One important goal for PERFECT is that it may be used via the Systems Modeling Language (SysML) so that the SysML-defined model of the robot system is mapped to the actual implementation in ROS. Applications such as Magic Systems of Systems Architect, which can be used to simulate SysML-defined models, may control and receive data from ROS simulations, brokered by PERFECT. This is done with the RESTful API provided by PERFECT using Flask and is the same used in a browser.

An "experiment" is a combination of design, environment, and operation plan sufficient to run a ROS simulation to completion, with well-defined success and failure states (usually, these will be the result of a ROS action specified by the operation plan). Information about a robot's state or the state of its environment can be collected and analysed in real time; the results of these analyses may inform decisions about cancelling an experiment early if a failure state (defined at a higher level than the ROS action) is reached or, potentially, simulating human intervention or environmental changes.

PERFECT uses a SQLite database to maintain the definitions of components, designs, environmental/instructional components, and experiments.

## Dependencies and Installation

Use the same Python environment that ROS uses (i.e., the same that has `rclpy`, etc.). PERFECT is installed via
`python -m pip install -e .`

Redis.

## Running the demo projects

The Redis server must be running. If it is not already, you can run `redis-server` in a terminal.

In all other terminals, you must do a few things:
- Set the environment variable `PERFECT_PROJECT_ROOT` to the absolute path, like `/path/to/perfect/examples/ros2-turtlebot3`.
- Make this your current working directory, like with `cd $PERFECT_PROJECT_ROOT`.

To initialize the database and fill the components table, follow these steps:
- `python -m flask --app perfect.app db init`
- `python -m flask --app perfect.app db migrate -m "Initial migration."`
- `python -m flask --app perfect.app db upgrade`
- `python -m flask --app perfect.app components load components.json`

You can always remove the database with `rm -rf migrations/ *.db*` and start fresh.

Start the RQ worker with `rq worker perfect-tasks` in a terminal. This will handle the delegation of individual experiments from start to finish.

Start a PERFECT runner with `python -m perfect.experiment.runner` in a terminal. This is the part of PERFECT that will actually run ROS.

Start the PERFECT server with `python -m flask --app perfect.app run`. You can then go to `http://localhost:5000` in a browser. To see this from another machine, you need to add `--host 0.0.0.0` to this command.
