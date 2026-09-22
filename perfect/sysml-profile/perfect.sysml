// PERFECT SysML v2 profile.
//
// A textual library package declaring the metadata this binding needs: a ROS 2
// node, topic and parameter, and the ComponentImplementation that PERFECT's
// library stores. The attribute names mirror
// perfect/app/schema/implementation_schema.json one for one, so a model
// annotated with these produces the same JSON PERFECT already validates.
//
// PERFECT does not parse this file. The SysML path that runs today is v1:
// the mk6 model in Magic Systems of Systems Architect, driven through Magic
// Model Analyst and the MATLAB bridge in sysml/workbench/bridge/ to
// POST /api/v1/run. This is the API-first counterpart, written down so the
// vocabulary is fixed before anyone writes the reader.
//
// It has not been run through a SysML v2 parser: there is none on this
// workstation.
//
// See perfect/docs/sysml-binding.md for the mapping this file encodes.

library package PERFECT {
    doc
    /*
     * Metadata binding SysML parts to ROS 2 elements and to PERFECT's
     * component library.
     */

    private import ScalarValues::*;

    // --------------------------------------------------------------
    // the pieces of an implementation JSON

    attribute def EnvironmentVariable {
        doc /* One entry of the implementation's "envvars" array. */
        attribute envvar : String;
        attribute envvarValue : String;
    }

    attribute def LaunchArgument {
        doc /* One entry of "launchargs"; becomes arg:=value on the launch command. */
        attribute arg : String;
        attribute argValue : String;
    }

    attribute def FileUpdate {
        doc
        /*
         * One entry of "files". keys is the dotted key path into a YAML file,
         * or the prim path into a USD stage. file is the alias the experiment
         * class declares in its _files mapping, not a filesystem path.
         */
        attribute file : String;
        attribute keys : String;
        attribute updateValue : String;
    }

    attribute def ImplementationParameter {
        doc
        /*
         * One entry of "parameters". PERFECT substitutes defaultValue for
         * $name everywhere in the implementation when a design is built.
         */
        attribute name : String;
        attribute defaultValue : String;
    }

    // --------------------------------------------------------------
    // ROS 2 elements

    metadata def ROS2Node {
        doc /* The ROS 2 node a part is realized by. */
        attribute packageName : String;
        attribute executable : String;
        attribute nodeName : String;
        attribute nodeNamespace : String;
    }

    metadata def ROS2Topic {
        doc /* A topic the node publishes or subscribes to. */
        attribute topicName : String;
        attribute messageType : String;
        attribute published : Boolean;
        attribute expectedRateHz : Real;
    }

    metadata def ROS2Parameter {
        doc
        /*
         * A ROS 2 parameter. parameterFile and keyPath say where PERFECT
         * writes it: the file alias and the dotted key path inside it.
         */
        attribute parameterName : String;
        attribute parameterValue : String;
        attribute parameterFile : String;
        attribute keyPath : String;
    }

    // --------------------------------------------------------------
    // the library row

    metadata def ComponentImplementation {
        doc
        /*
         * One row of PERFECT's component_implementation table. componentName
         * is the name the library is matched on, including by
         * POST /api/v1/run; componentType is the type the sensor_update keys
         * of that endpoint match against (laser_3d, laser_2d, camera,
         * depth_camera, planner, controller, ...).
         */
        attribute componentName : String;
        attribute componentType : String;
        attribute envvars : EnvironmentVariable[0..*];
        attribute launchArgs : LaunchArgument[0..*];
        attribute fileUpdates : FileUpdate[0..*];
        attribute parameters : ImplementationParameter[0..*];
    }
}

// ------------------------------------------------------------------
// one worked example

package PerfectSensorSuiteExample {
    private import PERFECT::*;
    private import ScalarValues::*;

    part def LiDAR {
        doc /* The datasheet: these become columns of PERFECT's component table. */
        attribute channels : Integer;
        attribute rotationRateMaxHz : Real;
        attribute rangeMaxM : Real;
        attribute powerW : Real;
    }

    part def GroundRobot {
        part lidar : LiDAR;
    }

    @ROS2Node {
        packageName = "velodyne_driver";
        executable = "velodyne_driver_node";
        nodeName = "velodyne_driver";
        nodeNamespace = "/";
    }
    @ComponentImplementation {
        componentName = "Velodyne Puck (15 Hz)";
        componentType = "laser_3d";
        envvars = (
            EnvironmentVariable(envvar = "HUSKY_LASER_3D_ENABLED", envvarValue = "true"),
            EnvironmentVariable(envvar = "HUSKY_LASER_3D_TOPIC", envvarValue = "velodyne_points")
        );
        launchArgs = (
            LaunchArgument(arg = "lidar3d", argValue = "true")
        );
        fileUpdates = (
            FileUpdate(file = "sensor.yaml", keys = "laser_3d", updateValue = "vlp16")
        );
    }
    part velodynePuck : LiDAR {
        attribute :>> channels = 16;
        attribute :>> rotationRateMaxHz = 15.0;
        attribute :>> rangeMaxM = 100.0;
        attribute :>> powerW = 80.0;

        @ROS2Topic {
            topicName = "/velodyne_points";
            messageType = "sensor_msgs/msg/PointCloud2";
            published = true;
            expectedRateHz = 15.0;
        }

        @ROS2Parameter {
            parameterName = "rpm";
            parameterValue = "900";
            parameterFile = "sensor.yaml";
            keyPath = "laser_3d.update_rate";
        }
    }

    part agr : GroundRobot {
        part :>> lidar = velodynePuck;
    }
}
