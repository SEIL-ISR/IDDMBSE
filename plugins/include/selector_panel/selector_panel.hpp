/*
 *
 */

#ifndef SELECTOR_PANEL__SELECTOR_PANEL_HPP_
#define SELECTOR_PANEL__SELECTOR_PANEL_HPP_

#include <memory>

#include <QtWidgets>
#include <QString>

#include "rviz_common/panel.hpp"
#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/string.hpp"

namespace selector_panel
{
    class SelectorPanel : public rviz_common::Panel
    {
        Q_OBJECT

        public:
            explicit SelectorPanel(QWidget* parent=nullptr);
            ~SelectorPanel();

        private Q_SLOTS:
            void on_select_controller(const QString& text);
            void on_select_planner(const QString& text);
            void on_path_return();
        
        private:
            rclcpp::Node::SharedPtr node_;
            std::string curr_controller_;
            std::string curr_planner_;
            std::vector<std::string> controllers_;
            std::vector<std::string> planners_;
    
            rclcpp::Publisher<std_msgs::msg::String>::SharedPtr controller_pub_;
            rclcpp::Publisher<std_msgs::msg::String>::SharedPtr planner_pub_;

            QVBoxLayout* main_layout_{nullptr};
            QHBoxLayout* controller_layout_{nullptr};
            QHBoxLayout* planner_layout_{nullptr};
            QComboBox* controller_box_{nullptr};
            QComboBox* planner_box_{nullptr};
    };
}

#endif // SELECTOR_PANEL__SELECTOR_PANEL_HPP_