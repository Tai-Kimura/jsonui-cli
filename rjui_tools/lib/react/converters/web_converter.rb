# frozen_string_literal: true

require_relative 'base_converter'

module RjuiTools
  module React
    module Converters
      class WebConverter < BaseConverter
        def convert(indent = 2)
          class_name = build_class_name
          style_attr = build_style_attr
          id_attr = build_id_attr
          testid_attr = build_testid_attr
          tag_attr = build_tag_attr

          # Build iframe attributes
          src = build_src_attr
          sandbox_attr = build_sandbox_attr
          allow_attr = build_allow_attr
          title_attr = build_title_attr
          loading_attr = build_loading_attr

          jsx = "#{indent_str(indent)}<iframe#{id_attr} className=\"#{class_name}\"#{src}#{title_attr}#{sandbox_attr}#{allow_attr}#{loading_attr}#{style_attr}#{testid_attr}#{tag_attr} />"

          wrap_with_visibility(jsx, indent)
        end

        protected

        def build_class_name
          classes = [super]

          # Default border none for iframe
          classes << 'border-0'

          # Scrolling behavior
          scrolling = json['scrollEnabled']
          classes << 'overflow-hidden' if scrolling == false

          classes.compact.reject(&:empty?).join(' ')
        end

        def build_src_attr
          url = json['url'] || json['src']
          html = json['html'] || json['htmlContent']

          if url
            if has_binding?(url)
              " src={#{extract_binding_property(url)}}"
            else
              " src=\"#{url}\""
            end
          elsif html
            # For HTML content, use srcdoc
            if has_binding?(html)
              " srcDoc={#{extract_binding_property(html)}}"
            else
              escaped_html = html.gsub('"', '&quot;')
              " srcDoc=\"#{escaped_html}\""
            end
          else
            ''
          end
        end

        def build_sandbox_attr
          # Check if sandbox should be disabled entirely
          return '' if json['sandbox'] == false

          # Build sandbox permissions based on JSON config
          permissions = []

          # JavaScript enabled
          permissions << 'allow-scripts' if json['javaScriptEnabled'] != false

          # Allow same origin for most functionality
          permissions << 'allow-same-origin'

          # Allow popups if JavaScript can open windows
          permissions << 'allow-popups' if json['javaScriptCanOpenWindowsAutomatically']

          # Allow popups to escape sandbox
          permissions << 'allow-popups-to-escape-sandbox' if json['allowPopupsToEscapeSandbox']

          # Allow forms
          permissions << 'allow-forms'

          # Allow modals
          permissions << 'allow-modals' if json['allowModals']

          # Allow downloads
          permissions << 'allow-downloads' if json['allowDownloads']

          return '' if permissions.empty?

          " sandbox=\"#{permissions.join(' ')}\""
        end

        def build_allow_attr
          allows = []

          # Inline media playback
          allows << 'autoplay' if json['allowsInlineMediaPlayback']

          # Fullscreen
          allows << 'fullscreen' if json['allowsFullScreen'] != false

          # Camera/Microphone
          allows << 'camera' if json['allowCamera']
          allows << 'microphone' if json['allowMicrophone']

          # Geolocation
          allows << 'geolocation' if json['allowGeolocation']

          return '' if allows.empty?

          " allow=\"#{allows.join('; ')}\""
        end

        def build_title_attr
          title = json['title'] || json['accessibilityLabel']
          return '' unless title

          " title=\"#{title}\""
        end

        def build_loading_attr
          lazy = json['lazyLoad'] || json['loading']
          return '' unless lazy

          ' loading="lazy"'
        end
      end
    end
  end
end
