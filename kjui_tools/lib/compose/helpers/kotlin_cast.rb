# frozen_string_literal: true

module KjuiTools
  module Compose
    module Helpers
      # `<subject> as? <type>` for the generated Kotlin.
      #
      # A cast to a generic type the runtime cannot check — Map<String, Any?>,
      # List<Any?> — is an "unchecked cast" warning, an error in an app built
      # with allWarningsAsErrors (kjui-map-list-data-bindings-warn-under-all-
      # warnings-as-errors). The cast is what the value needs, so the warning is
      # suppressed on that expression alone — where no enclosing function
      # carries the suppression (a class-list's items; the Data's fromMap and
      # the ViewModel's updateData suppress it on the function). A star
      # projection (List<*>) is checked and stays as it is.
      module KotlinCast
        def self.as_nullable(subject, kotlin_type)
          cast = "#{subject} as? #{kotlin_type}"
          args = kotlin_type[/<(.*)>/, 1]
          return cast if args.nil? || args.split(',').all? { |arg| arg.strip == '*' }

          "(@Suppress(\"UNCHECKED_CAST\") (#{cast}))"
        end
      end
    end
  end
end
