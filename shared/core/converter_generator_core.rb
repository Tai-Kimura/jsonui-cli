# frozen_string_literal: true

require 'fileutils'
require 'json'
require_relative 'attribute_validator_core'
require_relative 'attribute_types'

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
  #     ⚠️ Written 2026-08-01 and FALSE until 1.8.113 for sjui and kjui:
  #     this core honoured the options, but only rjui's CLI parsed them —
  #     `sjui/kjui g converter --force` was "invalid option". 1.8.112's
  #     scaffold header repeated the claim; 1.8.113 made the two CLIs parse
  #     both flags, so the sentence is now true.
  #   - the extension attribute-definition JSON carries the _generated
  #     marker everywhere (was sjui-only; the file is rewritten on every
  #     run, so the generated-file invariant applies)
  #   - type strings are normalized before schema mapping (rjui semantics):
  #     `String?` / `[Int]` from component specs map to real types instead
  #     of falling through to the binding-only branch
  class ConverterGeneratorCore
    # THE ONE OVERWRITE DECISION for every file a `g converter` run writes:
    # the converter here, and the files the platform sub-generators write
    # beside it (the Swift / Kotlin component, adapters, view adapters).
    # Returns true when `file_path` may be written.
    #
    # Until 1.8.112 only the converter came through here. The six
    # sub-generators each kept their own `print "Overwrite? (y/n)"` +
    # `gets.chomp`, so `--skip-existing` / JUI_SKIP_EXISTING (which
    # `jui g converter --skip-existing` exports) and `--force` stopped at the
    # converter: a re-scaffold still waited on stdin for each existing
    # component and adapter, and with stdin closed `gets` returned nil and
    # `nil.chomp` raised (reported 2026-09-24). Here stdin EOF is "n" — the
    # safe side, since those files are the ones people maintain by hand.
    #
    # `noun` / `exists_label` name the file in the two log lines, so the
    # converter's lines read as they always have.
    #
    # A `g converter` run also records here what it wrote and what it kept
    # (track_scaffold_files starts the record; the sub-generators get this
    # options hash or a merge of it, and a merge shares the record), so what
    # follows the scaffold can read what the kept files say — see
    # kept_leaf_scaffold.
    def self.may_write?(file_path, options, logger, noun:, exists_label: nil)
      write = overwrite_decision(file_path, options, logger, noun: noun, exists_label: exists_label)
      record = options[:scaffold_files]
      record[write ? :written : :kept] << file_path if record.is_a?(Hash)
      write
    end

    def self.overwrite_decision(file_path, options, logger, noun:, exists_label:)
      return true unless File.exist?(file_path)

      if ENV['JUI_SKIP_EXISTING'] == '1' || options[:skip_existing]
        logger.info "Skipped existing #{noun}: #{file_path}"
        return false
      end
      return true if options[:force]

      logger.warn "#{exists_label || noun.capitalize} already exists: #{file_path}"
      print "Overwrite? (y/n): "
      $stdin.gets&.chomp&.downcase == 'y'
    end
    private_class_method :overwrite_decision

    # `--attribute-descriptions '<json>'`: {attribute name => description},
    # the component spec's `props.items[].description`, which `jui g
    # converter --from / --all` hands down. Returns the Hash, or raises
    # ArgumentError naming what is wrong (the CLIs print it and exit 1).
    #
    # Until 1.8.113 the spec's descriptions never left `jui`: it passed
    # `name:type` only, and every rewrite of attribute_definitions/<Name>.json
    # replaced hand-written descriptions with "<key> attribute".
    def self.parse_attribute_descriptions(json_text)
      parsed = JSON.parse(json_text.to_s)
      unless parsed.is_a?(Hash) && parsed.all? { |k, v| k.is_a?(String) && v.is_a?(String) }
        raise ArgumentError, "--attribute-descriptions takes a JSON object of " \
                             "{\"attribute\": \"description\"}"
      end
      parsed
    rescue JSON::ParserError => e
      raise ArgumentError, "--attribute-descriptions is not valid JSON (#{e.message.lines.first&.strip})"
    end

    # The description an attribute definition carries: the spec's when one
    # was handed down, the placeholder otherwise.
    def self.attribute_description(options, key, fallback)
      descriptions = options && options[:attribute_descriptions]
      text = descriptions.is_a?(Hash) ? descriptions[key] : nil
      text.is_a?(String) && !text.strip.empty? ? text : fallback
    end

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

      # `jui build` (and other non-interactive flows) set JUI_SKIP_EXISTING=1
      # so the prompt is bypassed and existing converter files are left alone.
      # `--skip-existing` is the CLI equivalent; `--force` overwrites.
      return unless self.class.may_write?(file_path, @options, @logger,
                                          noun: 'converter',
                                          exists_label: 'Converter file')

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

    # Names every attribute whose type is outside the shared vocabulary
    # (attribute_types.rb) and what it was scaffolded as — the same sentence
    # on every tool. Not a refusal: faces declare their own model types
    # (`[AppRow]`, `Date`), and refusing stopped `jui g converter --all` on
    # three of them (measured 2026-09-26).
    #
    # Called AFTER the scaffold: whether it was written or kept is known only
    # then, and a run that wrote none says "kept" instead of "is scaffolded
    # as" (until 1.8.121 it was called first and said "is scaffolded as" of
    # files it went on to keep — ticket converter-attr-types-warning-wording).
    def warn_outside_attribute_types
      kept = typed_scaffold_kept?
      JsonUIShared::AttributeTypes.outside(@options[:attributes]).each do |key, type|
        @logger.warn JsonUIShared::AttributeTypes.outside_warning(key, type, kept: kept)
      end
    end

    # Whether this run kept the files that declare the attribute types (the
    # component, and the Dynamic adapter / wrapper — not the converter, which
    # declares none) and wrote none of them. false when nothing was recorded.
    def typed_scaffold_kept?
      record = @options[:scaffold_files]
      return false unless record.is_a?(Hash)

      converter = File.expand_path(converter_file_path)
      typed = ->(paths) { paths.reject { |path| File.expand_path(path) == converter } }
      typed.call(record[:written]).empty? && !typed.call(record[:kept]).empty?
    end

    # `--container` / `--no-container` change what a component declares about
    # children; a run with neither keeps the declaration it already has. Until
    # 1.8.121 a run with neither rewrote the definition in the default form
    # over a leaf's `"_children": "none"` — `jui g converter --all`, with or
    # without --skip-existing, which does not read a leaf from a component
    # spec — and the build stopped refusing the leaf's children while its
    # scaffold went on dropping them, with no warning (measured 2026-09-26).
    # Called first (after track_scaffold_files), so the converter, the
    # scaffolds and the definition of this run all follow the kept
    # declaration.
    def keep_children_declaration
      return unless @options[:is_container].nil?
      return unless declared_children == AttributeValidatorCore::NO_CHILDREN

      @options[:is_container] = false
      @logger.info "#{@name} is declared a leaf in attribute_definitions/#{@name}.json — kept " \
                   '(pass --container to change it)'
    end

    # What attribute_definitions/<Name>.json said about children before this
    # run wrote it: nil when the file or the key is absent, or the file cannot
    # be read. Read once (the run writes the file last).
    def declared_children
      return @declared_children if defined?(@declared_children)

      @declared_children = read_declared_children
    end

    def read_declared_children
      path = File.join(attr_defs_dir, "#{@name}.json")
      return nil unless File.file?(path)

      definition = JSON.parse(File.read(path))[@name]
      definition.is_a?(Hash) ? definition[AttributeValidatorCore::CHILDREN_DECLARATION] : nil
    rescue JSON::ParserError => e
      @logger.warn "attribute_definitions/#{@name}.json is not JSON (#{e.message.lines.first.to_s.strip}) — " \
                   'what it declared about children cannot be kept; pass --container or --no-container'
      nil
    end

    # Called first by each profile's `generate`: from here on may_write?
    # records every scaffold file this run writes and every one it keeps.
    def track_scaffold_files
      @options[:scaffold_files] = { written: [], kept: [] }
    end

    # What a kept file says when it is in the leaf form: the code
    # `--no-container` writes, and only it.
    LEAF_FORMS = [
      # the converter (sjui / kjui / rjui): draws the component without them
      [/^\s*is_container = false\s*$/, 'draws %s without the children a layout gives it'],
      # sjui's Dynamic adapter, kjui's Dynamic wrapper: an error in their place
      ['var acceptsChildren: Bool { false }', 'refuses children in Dynamic mode'],
      ['private fun leafRejection(', 'refuses children in Dynamic mode']
    ].freeze

    # The files this run KEPT (--skip-existing, JUI_SKIP_EXISTING, "n", a
    # closed stdin) that are in the leaf form while the definition it is about
    # to write takes children: [[path, what the file does], ...].
    #
    # Until 1.8.121 a leaf turned back into a container — `--container`, or
    # `jui g converter --from` a spec that gained slots — with its scaffold
    # kept wrote `child` / `children` into the definition while the kept
    # converter went on drawing the component without them: the build
    # accepted the children and dropped them, rc 0, not a word (measured on
    # f16f3a11 on all three tools, 2026-09-26; ticket
    # leaf-turned-container-keeps-its-leaf-scaffold-silently). Written files
    # are not read: they are in the form this run asked for.
    def kept_leaf_scaffold
      return [] if @options[:is_container] == false

      record = @options[:scaffold_files]
      return [] unless record.is_a?(Hash)

      record[:kept].map { |path| [path, leaf_form(path)] }.select { |_, form| form }
    end

    # What `path` does as a leaf, or nil. Read as bytes: the markers are
    # ASCII, and the file may not be valid in the locale's encoding.
    def leaf_form(path)
      text = File.binread(path)
      LEAF_FORMS.each do |marker, what|
        found = marker.is_a?(Regexp) ? text.match?(marker) : text.include?(marker)
        return format(what, @name) if found
      end
      kept_view_leaf_form(path, text)
    rescue SystemCallError, IOError
      nil
    end

    # Profile hook: a kept component view that cannot draw children although
    # nothing in it says "leaf" (rjui's .tsx). nil: none.
    def kept_view_leaf_form(_path, _text)
      nil
    end

    # Names the kept leaf-form files, and answers whether the definition must
    # stay a leaf because of them. A leaf the build refuses children for is
    # the one of the two outcomes that is not silent; `--force` (or editing
    # the files) makes the component take children, `--no-container` keeps it
    # a leaf without this warning.
    def keep_leaf_for_kept_scaffold
      kept = kept_leaf_scaffold
      return false if kept.empty?

      mode = @options[:is_container] == true ? '--container' : 'the default mode'
      files = kept.map { |path, form| "#{display_path(path)} (#{form})" }.join(', ')
      @logger.warn "#{@name} would take children (#{mode}), but this run kept " \
                   "#{kept.size == 1 ? 'a file' : "#{kept.size} files"} in the leaf form: #{files}. " \
                   "attribute_definitions/#{@name}.json still declares a leaf, so the build refuses children " \
                   "given to #{@name} instead of dropping them. To make it take children, run again with " \
                   '--force (it overwrites them) or change them by hand; to keep it a leaf, pass --no-container.'
      true
    end

    def display_path(path)
      full = File.expand_path(path)
      base = File.join(File.expand_path(Dir.pwd), '')
      full.start_with?(base) ? full[base.size..-1] : full
    end

    # Generate attribute definition file for validation. Rewritten on every
    # run (unlike the scaffold, which is user-owned once generated), so it
    # carries the _generated marker on every platform.
    #
    # It also says whether the component takes children — this file is the
    # one place outside the user-owned scaffolds that a build reads:
    #   --container, and the default   `child` / `children` (both scaffold a
    #                                   content slot; the default's converter
    #                                   draws the children it is given)
    #   --no-container                  `"_children": "none"`, a leaf; the
    #                                   shared LayoutValidator refuses a
    #                                   layout that gives it children
    # Until 1.8.121 only --container declared anything, so the default read
    # as "no children" to the validator ("Unknown attribute 'child'") while
    # its children were drawn, and a leaf read the same — one sentence for
    # both outcomes. Written for every mode now, attributes or not: a leaf
    # with no attributes still has to say it is one.
    #
    # Written AFTER the scaffold: a run that takes children but kept files in
    # the leaf form writes a leaf (keep_leaf_for_kept_scaffold), and only the
    # scaffold step knows what it kept. Until 1.8.121 sjui wrote it before.
    def generate_attribute_definition_file
      has_attributes = @options[:attributes] && !@options[:attributes].empty?
      leaf = @options[:is_container] == false || keep_leaf_for_kept_scaffold

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

      if leaf
        attributes[AttributeValidatorCore::CHILDREN_DECLARATION] = AttributeValidatorCore::NO_CHILDREN
      else
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
        "description" => self.class.attribute_description(@options, actual_key,
                                                          "#{actual_key} attribute")
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
