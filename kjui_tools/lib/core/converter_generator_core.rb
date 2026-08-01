# frozen_string_literal: true

require 'fileutils'
require 'json'

module JsonUIShared
  # Shared body of the three `<tool> g converter` scaffolders: the
  # overwrite-safe converter-file writer, the registry (mappings file)
  # patcher, the extension attribute-definition JSON writer, and the
  # type-string → JSON-schema mapping. Canonical copy lives in
  # shared/core/converter_generator_core.rb; the per-tool copies under
  # <tool>/lib/core/ must stay byte-identical (pinned by each tool's
  # shared_core_mirror_spec — same contract as layout_validator).
  #
  # Platform truth stays in the profile
  # (<tool>/lib/{swiftui,compose,react}/generators/converter_generator.rb):
  # the constructor, the `generate` orchestration (platform sub-generators,
  # Xcode/initializer extras), the scaffold template itself, and these
  # hooks:
  #
  #   extensions_dir           where the scaffold + registry live (kjui
  #                            resolves relative to the tool copy, s/r
  #                            relative to the project cwd)
  #   converter_file_name      "<snake>_converter.rb" / "<snake>_component.rb"
  #   converter_template       the platform scaffold text
  #   registry_spec            how this tool's registry file is patched:
  #                            { file:, const:, mapping_line:,
  #                              initial_content:, require_line: (optional) }
  #   attr_defs_dir            attribute_definitions/ location
  #   command_string           the CLI invocation recorded in the marker
  #   json_marker(source:, generator:)  per-tool GeneratedMarker helper
  #
  # Unified 2026-08-01 (W3-2, file 3). Divergences resolved toward the
  # correct side:
  #   - the overwrite prompt reads $stdin.gets&.chomp (rjui semantics):
  #     plain gets crashed on nil at stdin EOF and could read ARGV files;
  #     --force / --skip-existing options work on every tool
  #   - the extension attribute-definition JSON carries the _generated
  #     marker everywhere (was sjui-only; the file is rewritten on every
  #     run, so the generated-file invariant applies)
  #   - type strings are normalized before schema mapping (rjui semantics):
  #     `String?` / `[Int]` from component specs map to real types instead
  #     of falling through to the binding-only branch
  class ConverterGeneratorCore
    private

    # ---- platform profile hooks (implemented by the per-tool subclass) ----

    def extensions_dir
      raise NotImplementedError, 'platform profile must define extensions_dir'
    end

    def converter_file_name
      raise NotImplementedError, 'platform profile must define converter_file_name'
    end

    def converter_template
      raise NotImplementedError, 'platform profile must define converter_template'
    end

    def registry_spec
      raise NotImplementedError, 'platform profile must define registry_spec'
    end

    def attr_defs_dir
      raise NotImplementedError, 'platform profile must define attr_defs_dir'
    end

    def command_string
      raise NotImplementedError, 'platform profile must define command_string'
    end

    def json_marker(source:, generator:)
      raise NotImplementedError, 'platform profile must define json_marker'
    end

    # -----------------------------------------------------------------------

    def converter_file_path
      File.join(extensions_dir, converter_file_name)
    end

    def create_converter_file
      FileUtils.mkdir_p(extensions_dir)

      file_path = converter_file_path

      if File.exist?(file_path)
        # `jui build` (and other non-interactive flows) set JUI_SKIP_EXISTING=1
        # so the prompt is bypassed and existing converter files are left alone.
        # `--skip-existing` is the CLI equivalent; `--force` overwrites.
        if ENV['JUI_SKIP_EXISTING'] == '1' || @options[:skip_existing]
          @logger.info "Skipped existing converter: #{file_path}"
          return
        end
        unless @options[:force]
          @logger.warn "Converter file already exists: #{file_path}"
          print "Overwrite? (y/n): "
          # gets returns nil on stdin EOF (non-interactive run) — treat
          # as "n" instead of crashing on nil.chomp.
          response = $stdin.gets&.chomp&.downcase
          return unless response == 'y'
        end
      end

      File.write(file_path, converter_template)
      @logger.info "Created converter file: #{file_path}"
    end

    def update_mappings_file
      spec = registry_spec
      mappings_file = spec[:file]

      # Create new mappings file if it doesn't exist
      if !File.exist?(mappings_file)
        create_initial_mappings_file
        return
      end

      # Read existing mappings
      content = File.read(mappings_file)

      # Check if mapping already exists
      if content.include?("'#{@name}' =>")
        @logger.warn "Mapping for '#{@name}' already exists in #{File.basename(mappings_file)}"
        return
      end

      # Add require statement if the tool's registry needs one (kjui maps
      # to class constants, so the class must be required; s/r map to
      # class-name strings and resolve lazily)
      require_line = spec[:require_line]
      if require_line && !content.include?(require_line)
        # Add require after other requires or at the beginning of the module
        if content =~ /^require_relative/
          # Add after the last require
          content.sub!(/^((?:require_relative.*\n)+)/) do
            "#{$1}#{require_line}\n"
          end
        else
          # Add before the module declaration
          content.sub!(/^(# Auto-generated.*\n)\n/) do
            "#{$1}\n#{require_line}\n\n"
          end
        end
      end

      # Add new mapping
      new_mapping = spec[:mapping_line]

      # Insert the new mapping before the closing brace of the mappings
      # constant (indentation differs per tool — capture and reuse it)
      content.sub!(/(#{spec[:const]} = \{.*?)(,?)(\s*)([ ]*\}\.freeze)/m) do
        existing_mappings = $1
        closing = $4

        # If there are existing mappings, add the new one with proper formatting
        if existing_mappings =~ /=>/
          # Ensure the last existing mapping has a comma, then add the new mapping
          "#{existing_mappings},\n#{new_mapping}\n#{closing}"
        else
          # First mapping
          "#{existing_mappings}\n#{new_mapping}\n#{closing}"
        end
      end

      File.write(mappings_file, content)
      @logger.info "Updated #{File.basename(mappings_file)} with new mapping"
    end

    def create_initial_mappings_file
      spec = registry_spec
      mappings_file = spec[:file]
      FileUtils.mkdir_p(File.dirname(mappings_file))

      File.write(mappings_file, spec[:initial_content])
      @logger.info "Created #{File.basename(mappings_file)} with initial mapping"
    end

    # Generate attribute definition file for validation. Rewritten on every
    # run (unlike the scaffold, which is user-owned once generated), so it
    # carries the _generated marker on every platform.
    def generate_attribute_definition_file
      # Skip if no attributes and not a container
      has_attributes = @options[:attributes] && !@options[:attributes].empty?
      is_container = @options[:is_container] == true
      return if !has_attributes && !is_container

      dir = attr_defs_dir
      FileUtils.mkdir_p(dir)

      # Build attribute definitions
      attributes = {}
      if has_attributes
        @options[:attributes].each do |key, type|
          # Remove @ prefix if this is a binding attribute
          actual_key = key.start_with?('@') ? key[1..-1] : key

          attributes[actual_key] = build_attribute_definition(actual_key, type)
        end
      end

      # Add child/children for container components
      if is_container
        attributes["child"] = { "type" => "array", "description" => "Child component(s)" }
        attributes["children"] = { "type" => "array", "description" => "Child components (alias for child)" }
      end

      # Build JSON structure (prefix with _generated marker so LLM/Agent tools
      # know the file is regenerated on every `<tool> g converter` run).
      json_content = {
        "_generated" => json_marker(
          source: @name,
          generator: command_string
        ),
        @name => attributes
      }

      # Write to file
      file_path = File.join(dir, "#{@name}.json")
      File.write(file_path, JSON.pretty_generate(json_content))

      @logger.info "Created attribute definition file: attribute_definitions/#{@name}.json"
    end

    # Normalize a type string that arrives from component specs (`String?`,
    # `[Int]?`, `Bool`, `MyType?` …) into a canonical descriptor so the
    # downstream case dispatches don't end up in a fallback branch and
    # drop `String?` on the binding-only / `.inspect` path.
    #
    # Returns { base: String, array: Boolean, optional: Boolean }.
    def normalize_type(type_str)
      s = type_str.to_s.strip
      optional = s.end_with?('?')
      s = s.chomp('?')
      array = s.start_with?('[') && s.end_with?(']')
      s = s[1..-2] if array
      s = s.chomp('?') # strip inner `Int?` inside `[Int?]`
      { base: s.downcase, array: array, optional: optional }
    end

    # Map type string to JSON schema type (supports binding for all types).
    # Normalizes optional/array suffixes first so `String?` and `[Int]?`
    # from component specs don't fall through to the binding-only branch.
    # @param type [String] The type string from options
    # @return [Array, String] JSON schema type(s) - array for binding support
    def map_type_to_json_type(type)
      t = normalize_type(type)
      return ['array', 'binding'] if t[:array]

      case t[:base]
      when 'string'
        ['string', 'binding']
      when 'int', 'integer', 'number', 'double', 'float'
        ['number', 'binding']
      when 'bool', 'boolean'
        ['boolean', 'binding']
      when 'color'
        # Color accepts a semantic key ("dark_brown_text") or a binding;
        # the platform color resolver handles both at runtime.
        ['string', 'binding']
      else
        # Custom class types must use binding syntax (@{propertyName})
        'binding'
      end
    end

    def build_attribute_definition(actual_key, type)
      {
        "type" => map_type_to_json_type(type),
        "description" => "#{actual_key} attribute"
      }
    end

    def to_snake_case(str)
      str.gsub(/([A-Z]+)([A-Z][a-z])/, '\1_\2')
         .gsub(/([a-z\d])([A-Z])/, '\1_\2')
         .downcase
    end

    # Reconstruct the CLI invocation for provenance markers when the CLI
    # layer didn't hand one down (prefix is e.g. "kjui g converter").
    def build_command_string(prefix)
      cmd = "#{prefix} #{@name}"
      if @options[:attributes] && !@options[:attributes].empty?
        attrs = @options[:attributes].map { |k, v| "#{k}:#{v}" }.join(",")
        cmd += " --attributes=\"#{attrs}\""
      end
      cmd += " --container" if @options[:is_container] == true
      cmd += " --no-container" if @options[:is_container] == false
      cmd
    end
  end
end
