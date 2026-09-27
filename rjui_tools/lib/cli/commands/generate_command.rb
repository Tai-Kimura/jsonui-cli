# frozen_string_literal: true

require 'json'
require 'fileutils'
require 'optparse'
require_relative '../../core/config_manager'
require_relative '../../core/frameworks'
require_relative '../../core/logger'
require_relative '../../core/converter_generator_core'

module RjuiTools
  module CLI
    module Commands
      class GenerateCommand
        def initialize(args, original_args = nil)
          @args = args
          @original_args = original_args || args.dup
          @config = Core::ConfigManager.load_config
        end

        # A missing name and an unknown type exit 1 (until 1.9.0 they said
        # the error and exited 0), and an option the command does not declare
        # is said in one line, exit 1 — until 1.9.0 `g view --force` ended
        # in an OptionParser::InvalidOption stack trace (ticket
        # generate-commands-overwrite-edited-files-and-ignore-their-flags).
        def execute
          if @args.empty?
            show_help
            return
          end

          type = @args.shift

          case type
          when 'view', 'v'
            options = parse_view_options
            generate_view(require_name(type), options)
          when 'component', 'c'
            options = parse_view_options
            generate_component(require_name(type), options)
          when 'collection', 'col'
            options = parse_overwrite_options
            generate_collection(require_name(type, usage: 'rjui g collection <CellName>'), options)
          when 'converter', 'conv'
            generate_converter
          else
            Core::Logger.error("Unknown generator type: #{type}")
            show_help
            exit 1
          end
        rescue OptionParser::ParseError => e
          Core::Logger.error("rjui g #{type}: #{e.message}")
          exit 1
        rescue SystemCallError, IOError => e
          # A write that fails midway (a read-only file, a full disk): said in
          # one line, exit 1, as sjui and kjui do — the files decided before
          # it have each been said. Until 1.9.0 a stack trace.
          Core::Logger.error("rjui g #{type}: #{e.message}")
          exit 1
        end

        private

        def require_name(type, usage: nil)
          name = @args.shift
          return name if name

          Core::Logger.error("Name is required for '#{type}'")
          Core::Logger.info("Usage: #{usage}") if usage
          exit 1
        end

        # Each scaffold file through the one overwrite decision the generate
        # commands of the three tools share: an existing file is the app's —
        # kept unless --force (or "y" at the prompt); a closed stdin and
        # --skip-existing keep it. Said as it is decided.
        def scaffold(path, options, noun, &content)
          FileUtils.mkdir_p(File.dirname(path))
          JsonUIShared::ConverterGeneratorCore.write_scaffold(
            path, options, Core::Logger, noun: noun, label: noun, exists_label: noun.sub(/\A\w/, &:upcase), &content
          )
        end

        def scaffold_options(options)
          options.merge(scaffold_files: JsonUIShared::ConverterGeneratorCore.scaffold_record)
        end

        def report(name, options)
          JsonUIShared::ConverterGeneratorCore.report_scaffold_record(name, options[:scaffold_files], Core::Logger)
        end

        def generate_view(name, options = {})
          with_viewmodel = options[:with_viewmodel]

          # Handle nested paths like "learn/components/View"
          path_parts = name.split('/')
          base_name = path_parts.last
          dir_parts = path_parts[0...-1]

          view_name = to_pascal_case(base_name)
          json_name = to_snake_case(base_name)

          # Convert directory parts to kebab-case
          kebab_dir_parts = dir_parts.map { |part| to_kebab_case(part) }
          kebab_path = (kebab_dir_parts + [to_kebab_case(base_name)]).join('/')

          layouts_dir = @config['layouts_directory']
          # Build nested path for JSON file
          json_dir = File.join(layouts_dir, "pages", *kebab_dir_parts)
          json_path = File.join(json_dir, "#{json_name}.json")

          # Each of the layout, the page and the ViewModel is decided on its
          # own: until 1.9.0 an existing layout ended the run, and a page or
          # a ViewModel that was missing beside it was not written.
          options = scaffold_options(options)

          # Build layout based on --with-viewmodel option
          if with_viewmodel
            layout = {
              'type' => 'View',
              'id' => "#{json_name}_page",
              'width' => 'matchParent',
              'orientation' => 'vertical',
              'child' => [
                { 'data' => [{ 'class' => "#{view_name}ViewModel", 'name' => 'viewModel' }] },
                {
                  'type' => 'View',
                  'id' => "#{json_name}_content",
                  'width' => 'matchParent',
                  'padding' => [48, 24],
                  'orientation' => 'vertical',
                  'background' => '#FFFFFF',
                  'child' => [
                    {
                      'type' => 'Label',
                      'text' => view_name,
                      'fontSize' => 32,
                      'fontWeight' => 'bold',
                      'fontColor' => '#23272F'
                    }
                  ]
                }
              ]
            }
          else
            layout = {
              'type' => 'View',
              'id' => "#{json_name}_page",
              'width' => 'matchParent',
              'orientation' => 'vertical',
              'child' => [
                {
                  'type' => 'View',
                  'id' => "#{json_name}_content",
                  'width' => 'matchParent',
                  'padding' => [48, 24],
                  'orientation' => 'vertical',
                  'background' => '#FFFFFF',
                  'child' => [
                    {
                      'type' => 'Label',
                      'text' => view_name,
                      'fontSize' => 32,
                      'fontWeight' => 'bold',
                      'fontColor' => '#23272F'
                    }
                  ]
                }
              ]
            }
          end

          scaffold(json_path, options, 'layout') { JSON.pretty_generate(layout) }

          # Generate page.tsx
          generate_page_file(view_name, kebab_path, with_viewmodel, options)

          # Generate ViewModel only if --with-viewmodel is specified
          if with_viewmodel
            generate_viewmodel_file(view_name, options)
          end

          report("view #{name}", options)
          Core::Logger.info('Run "rjui build" to generate the React component')
        end

        def generate_component(name, options = {})
          with_viewmodel = options[:with_viewmodel]

          # Handle nested paths like "cards/UserCard"
          path_parts = name.split('/')
          base_name = path_parts.last
          dir_parts = path_parts[0...-1]

          view_name = to_pascal_case(base_name)
          json_name = to_snake_case(base_name)

          layouts_dir = @config['layouts_directory']
          # Build nested path for JSON file under components/
          json_dir = File.join(layouts_dir, "components", *dir_parts)
          json_path = File.join(json_dir, "#{json_name}.json")
          options = scaffold_options(options)

          # Build layout based on --with-viewmodel option
          if with_viewmodel
            layout = {
              'type' => 'View',
              'id' => "#{json_name}_container",
              'orientation' => 'vertical',
              'child' => [
                { 'data' => [{ 'class' => "#{view_name}ViewModel", 'name' => 'viewModel' }] },
                {
                  'type' => 'Label',
                  'text' => view_name,
                  'fontSize' => 16,
                  'fontColor' => '#000000'
                }
              ]
            }
          else
            layout = {
              'type' => 'View',
              'id' => "#{json_name}_container",
              'orientation' => 'vertical',
              'child' => [
                {
                  'type' => 'Label',
                  'text' => view_name,
                  'fontSize' => 16,
                  'fontColor' => '#000000'
                }
              ]
            }
          end

          scaffold(json_path, options, 'component layout') { JSON.pretty_generate(layout) }

          # Generate ViewModel if --with-viewmodel is specified
          if with_viewmodel
            generate_component_viewmodel_file(view_name, options)
          end

          report("component #{name}", options)
          Core::Logger.info('Run "rjui build" to generate the React component')
        end

        # The project writes TypeScript (`typescript` true), else JavaScript —
        # as `rjui build` names its components (.tsx / .jsx). Until jsonui-cli
        # 1.9.0 the page and the ViewModel scaffolds were TypeScript whatever
        # the project was, and `rjui build` then followed the ViewModel's .ts
        # into its generated ViewModel base and hook.
        def typescript?
          @config['typescript'] ? true : false
        end

        def generate_page_file(view_name, kebab_path, with_viewmodel, options)
          # kebab_path can be nested like "learn/components/view"
          path_parts = kebab_path.split('/')
          page_dir = File.join('src', 'app', *path_parts)
          page_path = File.join(page_dir, typescript? ? 'page.tsx' : 'page.jsx')
          scaffold(page_path, options, 'page') do
            content = page_content(view_name, with_viewmodel)
            typescript? ? content : javascript_page(content, view_name)
          end
        end

        # The page for a JavaScript project: the TypeScript page without its
        # types — the type arguments, and the Data type from the import.
        def javascript_page(content, view_name)
          content.sub("useState<#{view_name}Data>(", 'useState(')
                 .sub("useRef<#{view_name}ViewModel | null>(null)", 'useRef(null)')
                 .sub("import { #{view_name}Data, create#{view_name}Data } from", "import { create#{view_name}Data } from")
        end

        def page_content(view_name, with_viewmodel)
          fw = Core::Frameworks.for(@config)
          if with_viewmodel
            page_content = <<~TSX
              #{fw.use_client_prefix}#{fw.router_hook_import_prefix}import { useRef, useState } from "react";
              import #{view_name} from "@/generated/components/#{view_name}";
              import { #{view_name}ViewModel } from "@/viewmodels/#{view_name}ViewModel";
              import { #{view_name}Data, create#{view_name}Data } from "@/generated/data/#{view_name}Data";

              export default function #{view_name}Page() {
              #{fw.router_hook_statement_line}  const [data, setData] = useState<#{view_name}Data>(create#{view_name}Data());
                const dataRef = useRef(data);
                dataRef.current = data;

                const viewModelRef = useRef<#{view_name}ViewModel | null>(null);
                if (!viewModelRef.current) {
                  viewModelRef.current = new #{view_name}ViewModel(
                    router,
                    () => dataRef.current,
                    setData
                  );
                }

                return <#{view_name} data={data} />;
              }
            TSX
          else
            page_content = <<~TSX
              #{fw.use_client_prefix}#{fw.router_hook_import_prefix}import { useState } from "react";
              import #{view_name} from "@/generated/components/#{view_name}";
              import { #{view_name}Data, create#{view_name}Data } from "@/generated/data/#{view_name}Data";

              export default function #{view_name}Page() {
              #{fw.router_hook_statement_line}  const [data, setData] = useState<#{view_name}Data>(create#{view_name}Data());

                return <#{view_name} data={data} />;
              }
            TSX
          end

          page_content
        end

        def generate_viewmodel_file(view_name, options)
          viewmodel_path = File.join('src', 'viewmodels', "#{view_name}ViewModel#{typescript? ? '.ts' : '.js'}")
          scaffold(viewmodel_path, options, 'ViewModel') { typescript? ? viewmodel_content(view_name) : javascript_viewmodel(view_name) }
        end

        # The ViewModel for a JavaScript project: the same class, untyped.
        def javascript_viewmodel(view_name)
          <<~JS
            // ViewModel for #{view_name}
            // This file is NOT auto-generated after initial creation - safe to edit

            import { #{view_name}ViewModelBase } from "@/generated/viewmodels/#{view_name}ViewModelBase";

            export class #{view_name}ViewModel extends #{view_name}ViewModelBase {
              constructor(router, getData, setData) {
                super(router, getData, setData);
                this.initializeEventHandlers();
              }

              // Override methods or add custom logic here
            }
          JS
        end

        def viewmodel_content(view_name)
          fw = Core::Frameworks.for(@config)
          viewmodel_content = <<~TS
            // ViewModel for #{view_name}
            // This file is NOT auto-generated after initial creation - safe to edit

            #{fw.router_type_import_prefix}import { #{view_name}Data } from "@/generated/data/#{view_name}Data";
            import { #{view_name}ViewModelBase } from "@/generated/viewmodels/#{view_name}ViewModelBase";

            export class #{view_name}ViewModel extends #{view_name}ViewModelBase {
              constructor(
                router: #{fw.router_type},
                getData: () => #{view_name}Data,
                setData: (data: #{view_name}Data | ((prev: #{view_name}Data) => #{view_name}Data)) => void
              ) {
                super(router, getData, setData);
                this.initializeEventHandlers();
              }

              // Override methods or add custom logic here
            }
          TS

          viewmodel_content
        end

        def generate_component_viewmodel_file(view_name, options)
          viewmodel_path = File.join('src', 'viewmodels', "#{view_name}ViewModel#{typescript? ? '.ts' : '.js'}")
          scaffold(viewmodel_path, options, 'ViewModel') { typescript? ? component_viewmodel_content(view_name) : javascript_viewmodel(view_name) }
        end

        def component_viewmodel_content(view_name)
          fw = Core::Frameworks.for(@config)
          viewmodel_content = <<~TS
            // ViewModel for #{view_name}
            // This file is NOT auto-generated after initial creation - safe to edit

            #{fw.router_type_import_prefix}import { #{view_name}Data } from "@/generated/data/#{view_name}Data";
            import { #{view_name}ViewModelBase } from "@/generated/viewmodels/#{view_name}ViewModelBase";

            export class #{view_name}ViewModel extends #{view_name}ViewModelBase {
              constructor(
                router: #{fw.router_type},
                getData: () => #{view_name}Data,
                setData: (data: #{view_name}Data | ((prev: #{view_name}Data) => #{view_name}Data)) => void
              ) {
                super(router, getData, setData);
                this.initializeEventHandlers();
              }

              // Override methods or add custom logic here
            }
          TS

          viewmodel_content
        end

        def parse_view_options
          options = {
            with_viewmodel: true
          }

          OptionParser.new do |opts|
            opts.on('--no-viewmodel', 'Skip ViewModel generation') do
              options[:with_viewmodel] = false
            end

            JsonUIShared::ConverterGeneratorCore.declare_overwrite_options(opts, options)
          end.parse!(@args)

          options
        end

        def parse_overwrite_options
          options = {}
          OptionParser.new do |opts|
            JsonUIShared::ConverterGeneratorCore.declare_overwrite_options(opts, options)
          end.parse!(@args)
          options
        end

        def generate_converter
          options = parse_converter_options
          name = @args.shift

          unless name
            Core::Logger.error("Name is required for 'converter'")
            Core::Logger.info("Usage: rjui g converter <Name> [--attributes key:type,...]")
            return
          end

          require_relative '../../react/generators/converter_generator'
          generator = React::Generators::ConverterGenerator.new(name, options, @config, converter_command_line)
          generator.generate
        end

        # The invocation recorded in the generated files' markers, without the
        # type argument ('converter') and without --attribute-descriptions: its
        # JSON is the component spec's text, which the sjui / kjui markers do
        # not record either. Recording it made the marker of every attribute
        # definition carry the spec's text, and with LANG unset a non-ASCII
        # argument is binary, which Ruby 2.6.10 could not write into the JSON
        # marker (Encoding::UndefinedConversionError, measured 2026-09-24).
        def converter_command_line
          kept = []
          skip_value = false
          (@original_args[1..] || []).each do |arg|
            if skip_value
              skip_value = false
            elsif arg == '--attribute-descriptions'
              skip_value = true
            elsif !arg.start_with?('--attribute-descriptions=')
              kept << arg
            end
          end
          "rjui g converter #{kept.join(' ')}"
        end

        def parse_converter_options
          options = {
            attributes: {},
            is_container: nil  # nil means auto-detect based on children
          }

          OptionParser.new do |opts|
            opts.on('--attributes ATTRS', 'Add attributes (comma-separated key:type pairs)') do |attrs|
              split_top_level_commas(attrs).each do |attr|
                key, type = attr.strip.split(':', 2)
                if key && type
                  options[:attributes][key] = type
                else
                  Core::Logger.error("Invalid attribute format: #{attr}. Use key:type")
                  exit 1
                end
              end
            end

            opts.on('--container', 'Force component to be a container (handles children)') do
              options[:is_container] = true
            end

            opts.on('--no-container', 'Force component to not be a container (ignores children)') do
              options[:is_container] = false
            end

            # The component spec's prop descriptions, handed down by
            # `jui g converter --from / --all` so attribute_definitions/<Name>.json
            # keeps them instead of "<key> attribute".
            opts.on('--attribute-descriptions JSON', 'Descriptions for the attribute definition: {"attr": "text"}') do |json|
              begin
                options[:attribute_descriptions] = JsonUIShared::ConverterGeneratorCore.parse_attribute_descriptions(json)
              rescue ArgumentError => e
                Core::Logger.error(e.message)
                exit 1
              end
            end

            opts.on('--force', 'Overwrite existing converter/component files without prompting') do
              options[:force] = true
            end

            opts.on('--skip-existing', 'Leave existing converter/component files untouched (non-interactive)') do
              options[:skip_existing] = true
            end
          end.parse!(@args)

          options
        end

        # Split an --attributes list on top-level commas only. Spec prop
        # types can contain commas themselves (multi-arg closure types like
        # `((String, String) -> Void)?`) — commas nested in parens/brackets
        # belong to the type, not the list.
        def split_top_level_commas(str)
          parts = []
          depth = 0
          current = +''
          str.each_char do |ch|
            case ch
            when '(', '[' then depth += 1
            when ')', ']' then depth -= 1
            when ','
              if depth.zero?
                parts << current
                current = +''
                next
              end
            end
            current << ch
          end
          parts << current unless current.empty?
          parts
        end

        def to_pascal_case(string)
          # If already PascalCase (no separators), return as-is
          return string if string !~ /[-_\/]/ && string =~ /^[A-Z]/

          # Otherwise, split and capitalize each part
          string.split(/[-_\/]/).map { |part| part.sub(/^./, &:upcase) }.join
        end

        def to_snake_case(string)
          string
            .gsub(/([A-Z]+)([A-Z][a-z])/, '\1_\2')
            .gsub(/([a-z\d])([A-Z])/, '\1_\2')
            .downcase
            .gsub(/\//, '_')
        end

        def to_kebab_case(string)
          string
            .gsub(/([A-Z]+)([A-Z][a-z])/, '\1-\2')
            .gsub(/([a-z\d])([A-Z])/, '\1-\2')
            .downcase
            .gsub(/[_\/]/, '-')
        end

        def generate_collection(name, options = {})
          # Handle nested paths like "home/product_cell"
          path_parts = name.split('/')
          base_name = path_parts.last
          dir_parts = path_parts[0...-1]

          view_name = to_pascal_case(base_name)
          json_name = to_snake_case(base_name)

          layouts_dir = @config['layouts_directory']
          # Place under components/ (cells are components, not pages)
          json_dir = File.join(layouts_dir, 'components', *dir_parts)
          json_path = File.join(json_dir, "#{json_name}.json")
          options = scaffold_options(options)

          # Generate cell layout template (no ViewModel, no page)
          layout = {
            'type' => 'View',
            'id' => "#{json_name}_cell",
            'width' => 'matchParent',
            'orientation' => 'horizontal',
            'padding' => 12,
            'child' => [
              {
                'data' => [
                  { 'name' => 'title', 'class' => 'String', 'defaultValue' => 'Item' },
                  { 'name' => 'subtitle', 'class' => 'String', 'defaultValue' => 'Description' },
                  { 'name' => 'onCellTap', 'class' => '(() -> Void)?' }
                ]
              },
              {
                'type' => 'View',
                'orientation' => 'vertical',
                'weight' => 1,
                'child' => [
                  {
                    'type' => 'Label',
                    'text' => '@{title}',
                    'fontSize' => 16,
                    'fontWeight' => 'bold',
                    'fontColor' => '#333333',
                    'bottomMargin' => 4
                  },
                  {
                    'type' => 'Label',
                    'text' => '@{subtitle}',
                    'fontSize' => 13,
                    'fontColor' => '#666666'
                  }
                ]
              }
            ]
          }

          scaffold(json_path, options, 'collection cell') { JSON.pretty_generate(layout) }
          report("collection cell #{name}", options)
          Core::Logger.info("This is a component (no ViewModel/page generated)")
          Core::Logger.info("Use in a Collection's sections: { \"cell\": \"#{json_name}\" }")
          Core::Logger.info('Run "rjui build" to generate the React component')
        end

        def show_help
          puts <<~HELP
            Usage: rjui generate <type> <name> [options]

            Types:
              view, v           Generate a view layout (with page + ViewModel)
              component, c      Generate a component layout (no page, no ViewModel)
              collection, col   Generate a collection cell layout (no page, no ViewModel)
              converter, conv   Generate a custom converter

            Options for view/component:
              --no-viewmodel    Skip ViewModel generation (ViewModel is generated by default)

            Options for view/component/collection/converter:
              An existing file is kept: on a terminal the command asks first; any other stdin is not read.
              --force           Overwrite existing scaffold files without asking
              --skip-existing   Keep existing scaffold files without asking

            Options for converter:
              --attributes      Comma-separated key:type pairs (e.g., file:String,language:String)
              --container       Force component to be a container (handles children)
              --no-container    Force component to not be a container (ignores children)

            Examples:
              rjui g view HomeView
              rjui g view HomeView --no-viewmodel
              rjui g component UserCard
              rjui g component UserCard --no-viewmodel
              rjui g collection ProductCell
              rjui g collection home/ProductCell
              rjui g converter CodeBlock --attributes file:String,language:String
              rjui g converter Card --container
              rjui g converter Badge --no-container
          HELP
        end
      end
    end
  end
end
