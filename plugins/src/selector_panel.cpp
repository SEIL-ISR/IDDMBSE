/*
 *
 */

#include <chrono>
#include <memory>

#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QLabel>

#include "selector_panel/selector_panel.hpp"
#include "rclcpp/qos.hpp"
#include "rclcpp/parameter_client.hpp"

using namespace std::chrono_literals;

namespace selector_panel
{
    SelectorPanel::SelectorPanel(QWidget* parent) : Panel(parent)
    {
        node_=std::make_shared<rclcpp::Node>("selector_panel_node");
        
        auto parameters_client=std::make_shared<rclcpp::SyncParametersClient>(node_, "/controller_server");
        while (!parameters_client->wait_for_service(1s))
        {
            RCLCPP_INFO(node_->get_logger(), "service not available, waiting...");
        }
        controllers_=parameters_client->get_parameters({"controller_plugins"})[0].as_string_array();
        
        parameters_client.reset();
        parameters_client=std::make_shared<rclcpp::SyncParametersClient>(node_, "/planner_server");
        while (!parameters_client->wait_for_service(1s))
        {
            RCLCPP_INFO(node_->get_logger(), "service not available, waiting...");
        }
        planners_=parameters_client->get_parameters({"planner_plugins"})[0].as_string_array();

        main_layout_=new QVBoxLayout;
        controller_layout_=new QHBoxLayout;
        planner_layout_=new QHBoxLayout;
        controller_box_=new QComboBox;
        planner_box_=new QComboBox;

        for (std::string s:controllers_)
        {
            QString qstr = QString::fromStdString(s);
            controller_box_->addItem(qstr);
        }
        
        for (std::string s:planners_)
        {
            QString qstr = QString::fromStdString(s);
            planner_box_->addItem(qstr);
        }

        controller_layout_->addWidget(new QLabel("Controller Select"));
        controller_layout_->addWidget(controller_box_);
        planner_layout_->addWidget(new QLabel("Planner Select"));
        planner_layout_->addWidget(planner_box_);

        main_layout_->setContentsMargins(10, 10, 10, 10);
        main_layout_->addLayout(controller_layout_);
        main_layout_->addLayout(planner_layout_);

        setLayout(main_layout_);


        rmw_qos_profile_t custom_qos = rmw_qos_profile_default;
        custom_qos.history=RMW_QOS_POLICY_HISTORY_KEEP_LAST;
        //custom_qos.history=RMW_QOS_POLICY_HISTORY_KEEP_ALL;
        custom_qos.depth=1;
        custom_qos.reliability=RMW_QOS_POLICY_RELIABILITY_RELIABLE;
        //custom_qos.reliability=RMW_QOS_POLICY_RELIABILITY_BEST_EFFORT;
        //custom_qos.durability=RMW_QOS_POLICY_DURABILITY_VOLATILE;
        custom_qos.durability=RMW_QOS_POLICY_DURABILITY_TRANSIENT_LOCAL;

        auto qos = rclcpp::QoS(rclcpp::KeepLast(1), custom_qos);

        controller_pub_=node_->create_publisher<std_msgs::msg::String>("controller_selector", qos);
        planner_pub_=node_->create_publisher<std_msgs::msg::String>("planner_selector", qos);

        QObject::connect(controller_box_, SIGNAL(currentTextChanged(QString)), this, SLOT(on_select_controller(QString)));
        QObject::connect(planner_box_, SIGNAL(currentTextChanged(QString)), this, SLOT(on_select_planner(QString)));
    }

    SelectorPanel::~SelectorPanel() {}

    void SelectorPanel::on_select_controller(const QString& text)
    {
        std_msgs::msg::String msg;
        msg.data=text.toStdString();
        controller_pub_->publish(msg);
    }

    void SelectorPanel::on_select_planner(const QString& text)
    {
        std_msgs::msg::String msg;
        msg.data=text.toStdString();
        planner_pub_->publish(msg);
    }
}

#include <pluginlib/class_list_macros.hpp>
PLUGINLIB_EXPORT_CLASS(selector_panel::SelectorPanel, rviz_common::Panel)