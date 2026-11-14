# frozen_string_literal: true

# Every text component's emit calls `Configuration.Font.resolve(...)` (P1,
# ruling 2026-11-13: every text is the app's font), and a generated file
# imports it from the app's copy of lib/react/templates/Configuration.ts. A
# harness that strips the imports and runs or type-checks the emit on its own
# needs it too: these are the template's own, so a harness draws and checks
# what an app that sets no provider and no family gets.
module ConfigurationRuntime
  TEMPLATES = File.expand_path('../../lib/react/templates', __dir__)

  module_function

  # The JavaScript template with its `export` dropped: a script-scope
  # `Configuration` the stripped emit reads.
  def js
    File.read(File.join(TEMPLATES, 'js', 'Configuration.js')).gsub(/^export /, '')
  end

  # The same, as a statement that puts `Configuration` on globalThis: code a
  # harness runs through `new Function(...)` sees only globals, not the
  # script it is called from.
  def global_js
    "(() => {\n#{js}\nglobalThis.Configuration = Configuration;\n})();\n"
  end

  # TypeScript ambient declarations for a fragment compiled alone: the
  # template's FontSpec, and Configuration.Font.resolve over it.
  def declarations
    source = File.read(File.join(TEMPLATES, 'Configuration.ts'))
    spec = source[/^export interface FontSpec\s*\{.*?\n\}/m] or raise 'FontSpec not found in Configuration.ts'
    "#{spec.sub(/^export /, '')}\n" \
      "declare const Configuration: { Font: { resolve(spec: FontSpec): { [property: string]: string | number | undefined } } };\n"
  end
end
