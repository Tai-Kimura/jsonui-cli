# frozen_string_literal: true

require 'optparse'
require_relative '../../core/project_finder'

module SjuiTools
  module CLI
    module Commands
      class Convert
        def run(args)
          # Check for special subcommand 'to-group'
          if args.first == 'to-group'
            convert_to_group_reference(args[1..-1])
            return
          end
          
          options = parse_options(args)
          
          if args.empty?
            puts "Error: Input file or command is required"
            puts "Usage: sjui convert <input.json> [output.swift] [options]"
            puts "   or: sjui convert to-group [--force]"
            exit 1
          end
          
          input_file = args[0]
          output_file = args[1]
          
          unless File.exist?(input_file)
            puts "Error: Input file not found: #{input_file}"
            exit 1
          end
          
          # Determine conversion type based on options or file extension
          from_type = options[:from] || 'json'
          to_type = options[:to] || 'swiftui'
          
          case "#{from_type}-#{to_type}"
          when 'json-swiftui'
            convert_json_to_swiftui(input_file, output_file)
          else
            puts "Error: Unsupported conversion: #{from_type} to #{to_type}"
            exit 1
          end
        end

        private

        def parse_options(args)
          options = {}
          
          OptionParser.new do |opts|
            opts.banner = "Usage: sjui convert <input> [output] [options]"
            
            opts.on('--from TYPE', 'Input format (json)') do |type|
              options[:from] = type
            end
            
            opts.on('--to TYPE', 'Output format (swiftui)') do |type|
              options[:to] = type
            end
            
            opts.on('-h', '--help', 'Show this help message') do
              puts opts
              exit
            end
          end.parse!(args)
          
          options
        end

        def convert_to_group_reference(args)
          require_relative '../../uikit/tools/convert_to_group_reference'
          
          options = {}
          OptionParser.new do |opts|
            opts.banner = "Usage: sjui convert to-group [--force]"
            
            opts.on('--force', 'Force conversion even if already converted') do
              options[:force] = true
            end
            
            opts.on('-h', '--help', 'Show this help message') do
              puts opts
              exit
            end
          end.parse!(args)
          
          converter = SjuiTools::UIKit::Tools::ConvertToGroupReference.new
          converter.convert(options[:force])
        rescue => e
          puts "Error during conversion: #{e.message}"
          puts e.backtrace if ENV['DEBUG']
          exit 1
        end

        def convert_json_to_swiftui(input_file, output_file)
          require_relative '../../swiftui/json_to_swiftui_converter'
          
          puts "Converting #{input_file} to SwiftUI..."
          
          # Every include path resolves from the layouts root (U8) — when the
          # file is under a project's; otherwise (no project here: the lookup
          # raises) from its own directory, as a lone file always did.
          layouts_dir = begin
            config = Core::ConfigManager.load_config
            source_path = Core::ProjectFinder.get_full_source_path || Dir.pwd
            File.expand_path(File.join(source_path, config['layouts_directory'] || 'Layouts'))
          rescue StandardError
            nil
          end
          if layouts_dir && File.expand_path(input_file).start_with?(layouts_dir + File::SEPARATOR)
            SwiftUI::IncludeExpander.layouts_root = layouts_dir
          end

          converter = SwiftUI::JsonToSwiftUIConverter.new
          generated_file = converter.convert_file(input_file, output_file)
          
          puts "Conversion complete!"
          puts "Generated: #{generated_file}"
        rescue => e
          puts "Error during conversion: #{e.message}"
          puts e.backtrace if ENV['DEBUG']
          exit 1
        end
      end
    end
  end
end