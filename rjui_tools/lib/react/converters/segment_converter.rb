# frozen_string_literal: true

require_relative 'base_converter'
require_relative '../../core/attribute_validator_core'

module RjuiTools
  module React
    module Converters
      class SegmentConverter < BaseConverter
        def convert(indent = 2)
          class_name = build_class_name
          style_attr = build_style_attr
          id_attr = build_id_attr
          testid_attr = build_testid_attr
          tag_attr = build_tag_attr
          # Dropped entries are removed BEFORE the index is taken, so the
          # React `key` and the `{id}_tab_{n}` ids stay consecutive — the
          # runtimes compact too (mapNotNull / compactMap).
          items = declared_segment_items(attributes['items'] || [])

          selected_binding = build_selected_binding
          on_change = build_on_change
          disabled_attr = build_disabled_attr

          items_jsx = items.each_with_index.map do |item, index|
            button_class = build_button_class(index)
            button_disabled = attributes['enabled'] == false ? ' disabled' : ''
            # Data closure props are always optional (type_converter makes all
            # function types `| undefined`), so the call must be optional-chained.
            on_click_attr = on_change ? " onClick={() => #{on_change}?.(#{index})}" : ''
            # Item labels go through the same string resolution as Label.text
            # (string key -> binding -> literal), matching sjui's per-item
            # get_text_with_string_manager. The TEXT is taken first: an entry
            # in the canonical `{label, value}` form is a Hash, and a Hash
            # reached convert_text_binding, which passes non-Strings through
            # untouched — so Ruby's Hash#inspect went into the JSX as
            # `{"label"=>"opt_a", "value"=>"a"}` and the file did not parse.
            "#{indent_str(indent + 2)}<button key={#{index}}#{segment_item_id_attr(index)} className={`#{button_class}`}#{on_click_attr}#{button_disabled}>#{convert_text_binding(item)}</button>"
          end.join("\n")

          # `disabled` is not a valid attribute on <div>; reflect the state via
          # aria-disabled (each inner <button> carries the real disabled attr).
          jsx = <<~JSX.chomp
            #{indent_str(indent)}<div#{id_attr} className="#{class_name}"#{style_attr}#{testid_attr}#{tag_attr}#{build_aria_disabled_attr}>
            #{items_jsx}
            #{indent_str(indent)}</div>
          JSX

          wrap_with_visibility(jsx, indent)
        end

        protected

        # Per-button DOM id following the TabView `{id}_tab_{index}` naming
        # contract that the web test driver's selectTab action resolves.
        # Literal ids only — a bound id has no static value to interpolate.
        def segment_item_id_attr(index)
          seg_id = extract_id
          return '' if seg_id.nil? || has_binding?(seg_id)

          " id=\"#{seg_id}_tab_#{index}\""
        end

        def build_class_name
          classes = [super]

          classes << 'w-full'
          classes << 'flex'
          classes << 'rounded-lg'

          # Background color
          bg_color = attributes['backgroundColor']
          if bg_color
            classes << TailwindMapper.map_color(bg_color, 'bg')
          else
            classes << 'bg-gray-100'
          end

          classes << 'p-1'

          # Disabled state
          if attributes['enabled'] == false
            classes << 'opacity-50'
          elsif has_binding?(attributes['enabled'])
            binding_expr = extract_binding_property(attributes['enabled'])
            classes << "${!#{binding_expr} ? 'opacity-50' : ''}"
          end

          finalize_classes(classes)
        end

        # `Segment.items` is DECLARED as static label strings: the SSoT entry
        # carries no `items` sub-schema, where TabView.tabs and
        # Collection.sections declare `{"type": "object"}` explicitly when
        # they mean an object. Both dynamic runtimes agree — Android's
        # DynamicSegmentComponent keeps `isJsonPrimitive` and maps the rest to
        # null, iOS's `asStrings` keeps String/NSNumber and compacts the rest
        # away — so an object entry renders as nothing at runtime.
        #
        # Only the generator disagreed, and it did so by handing the Hash to
        # a text helper that passes non-Strings through: Ruby's Hash#inspect
        # went into the JSX as `{"label"=>"opt_a", "value"=>"a"}` and the
        # generated file stopped parsing, from a build that exited 0.
        #
        # So: keep what the declaration describes and drop the rest, as the
        # runtimes do. Taking `label` instead would give meaning to an input
        # the SSoT does not declare — that decision belongs to the
        # declaration, not to this converter.
        #
        # The drop is not silent: the shared validator names the entry, with
        # the layout path, on every path that reaches this converter (build /
        # watch / hotload all run BuildCommand, which validates). This
        # converter deliberately prints nothing of its own — two warnings for
        # one drop is noise, and only the validator has the path.
        #
        # The judgment is the shared one — `non_scalar_item_indices` is what
        # the validator uses to warn, so what is dropped here and what is
        # named there cannot drift apart. It is a no-op for every attribute
        # other than Segment.items, and for a non-Array value (`items` also
        # takes a binding string, which has no elements to drop).
        def declared_segment_items(items)
          # A bound `items` generates nothing. The declaration gives `items`
          # type array with NO binding, so there is no element list to walk;
          # sjui and kjui land on zero elements too, and the validator says
          # so. Measured on the extraction layer: `attributes['items']` is
          # already `[]` for a binding, so this asks the RAW value — the
          # emit decision comes from the shared rule, not from a coercion
          # that could change underneath it.
          if JsonUIShared::AttributeValidatorCore.binding_in_scalar_items?(
            'Segment', 'items', attributes.raw('items')
          )
            return []
          end

          return items unless items.is_a?(Array)

          drop = JsonUIShared::AttributeValidatorCore.non_scalar_item_indices(
            'Segment', 'items', items
          )
          return items if drop.empty?

          kept = []
          items.each_with_index do |item, index|
            next if drop.include?(index)

            kept << item
          end
          kept
        end

        def build_button_class(index)
          selected_index = with_bind_fallback(attributes['selectedIndex'] || attributes['selectedTabIndex']) || 0

          # Build font size class
          font_size_class = if attributes['fontSize']
            TailwindMapper.map_font_size(attributes['fontSize'])
          else
            'text-sm'
          end

          # Build padding class
          # height may be a keyword ("wrapContent" / "matchParent") — only a
          # numeric height can be translated into vertical padding.
          padding_class = if attributes['height'].is_a?(Numeric)
            "py-#{TailwindMapper::PADDING_MAP[attributes['height'] / 4] || (attributes['height'] / 4)}"
          else
            'py-2'
          end

          # Label colors. fontColor is the UNSELECTED label and selectedFontColor
          # the selected one, falling back to fontColor (contract:
          # semantics.segmentLabelColors). fontColor used to be the selected
          # label's fallback while the unselected one was hardcoded, so a dark
          # tint left the label unreadable with no way to declare otherwise.
          font_color = attributes['fontColor']
          unselected_text = font_color ? TailwindMapper.map_color(font_color, 'text') : 'text-gray-500 hover:text-gray-700'
          selected_font = attributes['selectedFontColor'] || font_color
          selected_text = selected_font ? TailwindMapper.map_color(selected_font, 'text') : 'text-gray-900'

          # tintColor is the selected-segment background accent
          # (UISegmentedControl heritage — sjui/kjui already render it).
          tint = attributes['tintColor']
          selected_bg = tint ? TailwindMapper.map_color(tint, 'bg') : 'bg-white'

          base_classes = "flex-1 px-4 #{padding_class} #{font_size_class} font-medium rounded-md transition-colors cursor-pointer"
          disabled_class = attributes['enabled'] == false ? ' cursor-not-allowed' : ''

          if has_binding?(selected_index)
            prop = extract_binding_property(selected_index)
            "#{base_classes}#{disabled_class} ${#{prop} === #{index} ? '#{selected_bg} #{selected_text} shadow' : '#{unselected_text}'}"
          else
            # Static selectedIndex — resolve the selected state at generation
            # time (the old code emitted a bare `selectedIndex` identifier,
            # which is undefined at runtime and crashed the component).
            selected_classes = if selected_index.to_i == index
                                 "#{selected_bg} #{selected_text} shadow"
                               else
                                 unselected_text
                               end
            "#{base_classes}#{disabled_class} #{selected_classes}"
          end
        end

        def build_selected_binding
          selected = with_bind_fallback(attributes['selectedIndex'] || attributes['selectedTabIndex'])

          if selected && has_binding?(selected)
            extract_binding_property(selected)
          else
            selected || 0
          end
        end

        # onChange handler expression, or nil when neither onValueChange nor a
        # selectedIndex binding provides one (static segment).
        def build_on_change
          handler = attributes['onValueChange']

          if handler && has_binding?(handler)
            extract_binding_property(handler)
          elsif attributes['valueChange'].is_a?(String) && !attributes['valueChange'].empty?
            # `valueChange` is the legacy SELECTOR spelling (a bare method
            # name, like `onclick`) that only the UIKit runtime read.
            add_viewmodel_data_prefix(to_camel_case(attributes['valueChange']))
          else
            # Generate setter from the raw binding name (without viewModel.data. prefix)
            selected = with_bind_fallback(attributes['selectedIndex'] || attributes['selectedTabIndex'])
            return nil unless selected && has_binding?(selected)

            raw_binding = extract_raw_binding_property(selected)
            setter_name = "set#{raw_binding[0].upcase}#{raw_binding[1..]}"
            add_viewmodel_data_prefix(setter_name)
          end
        end

        def build_disabled_attr
          enabled = attributes['enabled']
          return '' if enabled.nil?

          if has_binding?(enabled)
            " data-disabled={!#{extract_binding_property(enabled)}}"
          elsif enabled == false
            ' data-disabled="true"'
          else
            ''
          end
        end
      end
    end
  end
end
