# frozen_string_literal: true

module JsonUIShared
  # What a screen reader hears for each image of a layout — one rule for the
  # sjui and kjui codegen (the Dynamic runtimes of both libraries implement
  # the same rule, and all four run shared/core/image_accessibility_vectors
  # .json).
  #
  # `alt` (aliases `accessibilityLabel`, `contentDescription`) is the image's
  # spoken text: a strings.json key or literal, localized like `text`, or a
  # binding. An image is one of three roles:
  #
  #   label      — alt is a non-empty string: it is read.
  #   decorative — alt is "", or there is no alt and the image operates
  #                nothing: screen readers skip it (web alt="").
  #   control    — there is no alt and the image operates a control: it has a
  #                tap handler of its own, or it sits in the nearest tappable
  #                whose content names nothing (no text, no labelled image).
  #
  # A control image keeps what each platform read before alt existed (the id
  # on Android, the asset name on iOS), and the build names it (INFO). Hiding
  # it would take the control away from VoiceOver altogether: a tappable is a
  # `.onTapGesture`, not a Button, so with its only image hidden it has no
  # accessibility element left. That is the silence this rule chooses: a
  # control image reads an internal name until someone gives it an alt,
  # visibly (INFO) but without failing the build.
  module ImageAccessibility
    module_function

    # Image and its type aliases (component_metadata.json) plus NetworkImage.
    IMAGE_TYPES = %w[Image CircleImage CircleImageView ImageView Img NetworkImage].freeze

    # The canonical spelling first; the aliases are declared on `alt` in
    # attribute_definitions.json. A layout that `jui build` normalized
    # carries only `alt`.
    ALT_KEYS = %w[alt accessibilityLabel contentDescription].freeze

    # What a screen-reader user activates: a tap and a long press.
    TAP_KEYS = %w[onClick onclick onLongPress].freeze

    # Text that names a control when it sits inside it (string_manager_core's
    # STRING_PROPERTIES less `alt`, which is read off images below). On an
    # image, `hint` / `placeholder` name a placeholder IMAGE, not text.
    TEXT_KEYS = %w[text hint placeholder label prompt].freeze

    ROLE_KEY = '_imageRole'

    def image?(node)
      node.is_a?(Hash) && IMAGE_TYPES.include?(node['type'])
    end

    # The image's alt as written, or nil when it declares none. Spelled out
    # key by key, in ALT_KEYS order (the spec holds the two together), so
    # `jui conformance coverage` sees sjui and kjui read `alt` here.
    def alt(node)
      return node['alt'] if node.key?('alt')
      return node['accessibilityLabel'] if node.key?('accessibilityLabel')
      return node['contentDescription'] if node.key?('contentDescription')

      nil
    end

    def tappable?(node)
      node.is_a?(Hash) && TAP_KEYS.any? { |key| node.key?(key) }
    end

    def children(node)
      %w[child children].flat_map do |key|
        value = node[key]
        case value
        when Array then value.select { |c| c.is_a?(Hash) }
        when Hash then [value]
        else []
        end
      end
    end

    # True when something inside `node` (itself included) gives a control a
    # name: text on a non-image, or an image whose alt is not empty.
    def names_something?(node)
      if image?(node)
        value = alt(node)
        return value.is_a?(String) && !value.empty?
      end
      return true if TEXT_KEYS.any? { |key| node[key].is_a?(String) && !node[key].empty? }
      return true if node['items'].is_a?(Array) && node['items'].any? { |i| i.is_a?(String) && !i.empty? }

      children(node).any? { |c| names_something?(c) }
    end

    # The role of one image, given the tappables above it (nearest last).
    def role(node, tappable_ancestors = [])
      value = alt(node)
      return(value.to_s.empty? ? 'decorative' : 'label') unless value.nil?
      return 'control' if tappable?(node)

      nearest = tappable_ancestors.last
      return 'control' if nearest && !names_something?(nearest)

      'decorative'
    end

    # Writes ROLE_KEY on every image of an include-expanded tree and returns
    # one INFO per control image, in the LayoutValidator warning shape.
    def annotate!(root, source_path:)
      infos = []
      walk(root, []) do |node, tappables|
        node[ROLE_KEY] = role(node, tappables)
        next unless node[ROLE_KEY] == 'control'

        name = node['id'] || node['srcName'] || node['src'] || node['url'] || node['type']
        infos << {
          level: :info,
          message: "#{node['type']} '#{name}' operates a control and has no alt, so screen " \
                   'readers hear its id or asset name. Add alt: a strings.json key (or text) ' \
                   'that says what the control does.',
          location: source_path
        }
      end
      infos
    end

    def walk(node, tappables, &block)
      return unless node.is_a?(Hash)

      yield node, tappables if image?(node)
      inner = tappable?(node) ? tappables + [node] : tappables
      children(node).each { |c| walk(c, inner, &block) }
    end
  end
end
