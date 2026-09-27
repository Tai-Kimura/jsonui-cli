# frozen_string_literal: true

require_relative '../core/tap_accessibility'

module RjuiTools
  module React
    # A tap inside another tap is the inner one's alone. On iOS and Android
    # the innermost tap target takes the touch and the one around it never
    # sees it; on the web a click bubbles, so a Button inside a card that
    # opens on tap also opened the card. Through v1.8.120 the element handed
    # its handler the click event (`onClick={data.onTap}`) and a view model
    # could stop it; from 1.9.0 a handler is called as its data declares it
    # (BaseConverter#declared_tap_call), so an undeclared one gets nothing and
    # nothing stopped the click (jsonui-cli 1.9.1).
    #
    # stamp! writes KEY on every node with a click that sits inside another
    # node with a click, in one layout file. The tap form reads it
    # (BaseConverter#can_tap_gated_click) and stops the click there — unless
    # the tap hands the handler the event (a handler the data declares
    # `(Event)`, or the `name:` selector's sender): whoever gets the event
    # decides whether it goes on (ruled 2026-09-28).
    #
    # One file only: an include is its own component and a Collection's
    # cells are layouts of their own, so a tap there does not know what is
    # around its include site, and its click bubbles as it did in v1.8.120.
    module NestedTaps
      KEY = '_tapInsideTap'

      module_function

      # `root` annotated in place (react_generator runs it on its copy of the
      # layout, after validation, beside TapAccessibility.annotate!).
      def stamp!(root)
        walk(root, false, false)
        root
      end

      # A node the codegen gives a click: a tap (TapAccessibility.tappable?:
      # a handler, not disabled, canTap not false, not stopped) or the link
      # action, which is a click on the web too.
      def clicks?(node)
        return false unless node.is_a?(Hash)

        JsonUIShared::TapAccessibility.tappable?(node) || link_action?(node)
      end

      def link_action?(node)
        handler = node['onClick']
        handler.is_a?(Hash) && handler['action'] == 'link' && handler['url'] &&
          node['enabled'] != false && node['canTap'] != false && !JsonUIShared::TapAccessibility.stops?(node)
      end

      # `inside`: a node around this one has a click. `stopped`: a node
      # around it has `userInteractionEnabled: false` — nothing in there has
      # a click to stop, nor gives one to what it holds.
      def walk(node, inside, stopped)
        return unless node.is_a?(Hash)

        stopped ||= JsonUIShared::TapAccessibility.stops?(node)
        click = !stopped && clicks?(node)
        node[KEY] = true if click && inside
        JsonUIShared::TapAccessibility.children(node).each { |child| walk(child, inside || click, stopped) }
      end
    end
  end
end
