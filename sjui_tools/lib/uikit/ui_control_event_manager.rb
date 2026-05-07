# frozen_string_literal: true

module SjuiTools
  module UIKit
    class UIControlEventManager
      def initialize
        @ui_control_events = []
      end

      def reset
        @ui_control_events = []
      end

      def add_click_event(view_name, value, callback_type: nil)
        return if value == "nil"
        @ui_control_events << {
          view_name: view_name,
          value: value.sub(/^@\{/, "").sub(/\}$/, ""),
          event: "click",
          callback_type: callback_type
        }
      end

      def add_long_press_event(view_name, value)
        return if value == "nil"
        @ui_control_events << {
          view_name: view_name,
          value: value["closure"].sub(/^@\{/, "").sub(/\}$/, ""),
          duration: value["duration"],
          event: "longPress"
        }
      end

      def add_pan_event(view_name, value)
        return if value == "nil"
        @ui_control_events << {
          view_name: view_name,
          value: value.sub(/^@\{/, "").sub(/\}$/, ""),
          event: "pan"
        }
      end

      def add_pinch_event(view_name, value)
        return if value == "nil"
        @ui_control_events << {
          view_name: view_name,
          value: value.sub(/^@\{/, "").sub(/\}$/, ""),
          event: "pinch"
        }
      end

      # TextField event handlers
      def add_text_field_event(view_name, event_type, value, original_id: nil)
        return if value == "nil"
        @ui_control_events << {
          view_name: view_name,
          value: value.sub(/^@\{/, "").sub(/\}$/, ""),
          event: "textField",
          event_type: event_type,
          original_id: original_id
        }
      end

      # TextView event handlers
      def add_text_view_event(view_name, event_type, value, original_id: nil)
        return if value == "nil"
        @ui_control_events << {
          view_name: view_name,
          value: value.sub(/^@\{/, "").sub(/\}$/, ""),
          event: "textView",
          event_type: event_type,
          original_id: original_id
        }
      end

      def generate_bind_view_method
        return "" if @ui_control_events.size == 0

        content = String.new("\n")
        content << "    override func bindView() {\n"
        content << "        super.bindView()\n"

        @ui_control_events.each do |ce|
          case ce[:event]
          when "longPress"
            content << "        #{ce[:view_name]}?.#{ce[:event]}(duration: #{ce[:duration]}){ [weak self] gesture in self?.#{ce[:value]}?(gesture) }\n"
            content << "        #{ce[:view_name]}?.isUserInteractionEnabled = true\n"
          when "textField"
            content << generate_text_field_event(ce)
          when "textView"
            content << generate_text_view_event(ce)
          when "click"
            # onClick: callback is typically (() -> Void)? — no gesture argument needed
            content << "        #{ce[:view_name]}?.#{ce[:event]}{ [weak self] _ in self?.#{ce[:value]}?() }\n"
            content << "        #{ce[:view_name]}?.isUserInteractionEnabled = true\n"
          else
            # pan, pinch, etc.: callback takes gesture argument
            content << "        #{ce[:view_name]}?.#{ce[:event]}{ [weak self] gesture in self?.#{ce[:value]}?(gesture) }\n"
            content << "        #{ce[:view_name]}?.isUserInteractionEnabled = true\n"
          end
        end

        content << "    }\n"
        content
      end

      private

      def generate_text_field_event(ce)
        view_name = ce[:view_name]
        handler = ce[:value]
        event_type = ce[:event_type]

        case event_type
        when "onBeginEditing"
          "        #{view_name}?.onBeginEditing { [weak self] tf in self?.#{handler}?(tf) }\n"
        when "onEndEditing"
          "        #{view_name}?.onEndEditing { [weak self] tf in self?.#{handler}?(tf) }\n"
        when "onTextChange"
          "        #{view_name}?.onTextChange { [weak self] tf in self?.#{handler}?(\"#{ce[:original_id] || view_name}\", tf.text ?? \"\") }\n"
        when "onDeleteBackward"
          "        #{view_name}?.onDeleteBackward { [weak self] tf in self?.#{handler}?(tf) }\n"
        when "onShouldReturn"
          "        #{view_name}?.onShouldReturn { [weak self] tf in self?.#{handler}?(tf) ?? true }\n"
        when "onShouldChangeCharacters"
          "        #{view_name}?.onShouldChangeCharacters { [weak self] tf, range, string in self?.#{handler}?(tf, range, string) ?? true }\n"
        when "onShouldClear"
          "        #{view_name}?.onShouldClear { [weak self] tf in self?.#{handler}?(tf) ?? true }\n"
        when "onShouldBeginEditing"
          "        #{view_name}?.onShouldBeginEditing { [weak self] tf in self?.#{handler}?(tf) ?? true }\n"
        when "onShouldEndEditing"
          "        #{view_name}?.onShouldEndEditing { [weak self] tf in self?.#{handler}?(tf) ?? true }\n"
        when "onChangeSelection"
          "        #{view_name}?.onChangeSelection { [weak self] tf in self?.#{handler}?(tf) }\n"
        else
          ""
        end
      end

      def generate_text_view_event(ce)
        view_name = ce[:view_name]
        handler = ce[:value]
        event_type = ce[:event_type]

        case event_type
        when "onBeginEditing"
          "        #{view_name}?.onBeginEditing { [weak self] tv in self?.#{handler}?(tv) }\n"
        when "onEndEditing"
          "        #{view_name}?.onEndEditing { [weak self] tv in self?.#{handler}?(tv) }\n"
        when "onTextChange"
          "        #{view_name}?.onTextChange { [weak self] tv in self?.#{handler}?(\"#{ce[:original_id] || view_name}\", tv.text ?? \"\") }\n"
        when "onChangeSelection"
          "        #{view_name}?.onChangeSelection { [weak self] tv in self?.#{handler}?(tv) }\n"
        when "onShouldChangeText"
          "        #{view_name}?.onShouldChangeText { [weak self] tv, range, text in self?.#{handler}?(tv, range, text) ?? true }\n"
        when "onShouldBeginEditing"
          "        #{view_name}?.onShouldBeginEditing { [weak self] tv in self?.#{handler}?(tv) ?? true }\n"
        when "onShouldEndEditing"
          "        #{view_name}?.onShouldEndEditing { [weak self] tv in self?.#{handler}?(tv) ?? true }\n"
        else
          ""
        end
      end
    end
  end
end