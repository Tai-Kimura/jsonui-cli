# frozen_string_literal: true

require_relative 'binding_expression'
require_relative 'modifier_builder'

module KjuiTools
  module Compose
    module Helpers
      # `onLoadFailed` and `reloadToken` on a Web / WebView
      # (shared/core/attribute_definitions.json Web; both binding-only).
      #
      # Both are fed from the AndroidView `update` block, which runs again
      # whenever the data it reads changes — so the handler it hands over is
      # always the current one, and a moved token is seen on the next pass.
      # The state lives on the view (`KjuiWebLoadState.of`), because `update`
      # and the `KjuiWebViewClient` that reports failures share nothing else:
      # `WebView.getWebViewClient()` is API 26 and the library floor is 24.
      #
      # Emits nothing when neither attribute is a binding, so every existing
      # Web keeps a byte-identical `update` block.
      module WebLoadState
        def self.declared?(json_data)
          ModifierBuilder.is_binding?(json_data['onLoadFailed']) ||
            ModifierBuilder.is_binding?(json_data['reloadToken'])
        end

        # Unindented lines for the `update = { webView -> ... }` body.
        # `reload_call` re-loads the component's own source (its url, or its
        # html when it has no url) — not the page the user navigated to.
        def self.update_lines(json_data, reload_call)
          return [] unless declared?(json_data)

          # KjuiWebLoadState is new in the library, so this output does not
          # compile against an older one.
          lines = ['// Requires KotlinJsonUI >= 2.41.0 (Web onLoadFailed / reloadToken)',
                   'val loadState = KjuiWebLoadState.of(webView)']
          handler = json_data['onLoadFailed']
          if ModifierBuilder.is_binding?(handler)
            invocation = ModifierBuilder.get_event_handler_invocation(handler, json_data['id'], nil)
            lines << "loadState.onLoadFailed = { #{invocation} }"
          end
          token = json_data['reloadToken']
          if ModifierBuilder.is_binding?(token)
            value = BindingExpression.value_access(token[2..-2])
            lines << "if (loadState.reloadTokenChanged(#{value})) {"
            lines << "    #{reload_call}"
            lines << '}'
          end
          lines
        end
      end
    end
  end
end
