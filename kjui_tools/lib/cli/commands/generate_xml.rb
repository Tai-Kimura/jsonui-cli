#!/usr/bin/env ruby

require_relative '../../core/config_manager'
require_relative '../../xml/xml_generator'

module CLI
  module Commands
    class GenerateXml
      def self.run(args)
        puts "🔧 KotlinJsonUI XML Generator"
        puts "=============================="
        
        # Load configuration
        config = ConfigManager.load_config
        
        if config.nil?
          puts "❌ Error: config.json not found"
          puts "Run 'kjui init --mode xml' first to create configuration"
          return 1
        end
        
        # Check if XML mode is configured
        if config['mode'] != 'xml'
          puts "❌ Error: Project is configured for #{config['mode']} mode, not XML"
          puts "Run 'kjui init --mode xml' to reconfigure for XML mode"
          return 1
        end
        
        # Parse arguments
        layout_name = nil
        force = false
        
        i = 0
        while i < args.length
          case args[i]
          when '--layout', '-l'
            layout_name = args[i + 1]
            i += 1
          when '--force', '-f'
            force = true
          when '--help', '-h'
            show_help
            return 0
          else
            if layout_name.nil? && !args[i].start_with?('-')
              layout_name = args[i]
            end
          end
          i += 1
        end
        
        if layout_name.nil?
          # Generate all layouts
          generate_all_layouts(config, force)
        else
          # Generate specific layout
          generate_layout(layout_name, config, force)
        end
        
        0
      rescue => e
        puts "❌ Error: #{e.message}"
        puts e.backtrace if ENV['DEBUG']
        1
      end
      
      private
      
      def self.generate_all_layouts(config, force)
        layouts_dir = File.join(config['project_path'], 'app', 'src', 'main', 'assets', 'Layouts')
        
        unless Dir.exist?(layouts_dir)
          puts "❌ Error: Layouts directory not found: #{layouts_dir}"
          return
        end
        
        json_files = Dir.glob(File.join(layouts_dir, '*.json'))
        
        if json_files.empty?
          puts "❌ No JSON layout files found in #{layouts_dir}"
          return
        end
        
        puts "Found #{json_files.length} layout file(s)"
        puts ""
        
        success_count = 0
        json_files.each do |json_file|
          layout_name = File.basename(json_file, '.json')
          
          if should_generate?(layout_name, config, force)
            generator = XmlGenerator::Generator.new(layout_name, config)
            if generator.generate
              success_count += 1
            end
          else
            puts "⏭️  Skipping #{layout_name} (up to date)"
          end
        end
        
        puts ""
        puts "✅ Successfully generated #{success_count} XML layout(s)"
      end
      
      def self.generate_layout(layout_name, config, force)
        # Remove .json extension if present
        layout_name = layout_name.sub(/\.json$/, '')
        
        if should_generate?(layout_name, config, force)
          generator = XmlGenerator::Generator.new(layout_name, config)
          if generator.generate
            puts "✅ Successfully generated XML for #{layout_name}"
          else
            puts "❌ Failed to generate XML for #{layout_name}"
          end
        else
          puts "⏭️  Layout #{layout_name} is up to date (use --force to regenerate)"
        end
      end
      
      def self.should_generate?(layout_name, config, force)
        return true if force
        
        # Check modification times
        json_file = File.join(config['project_path'], 'app', 'src', 'main', 'assets', 'Layouts', "#{layout_name}.json")
        xml_file = File.join(config['project_path'], 'app', 'src', 'main', 'res', 'layout', "#{layout_name.downcase}.xml")
        
        return true unless File.exist?(xml_file)
        return true unless File.exist?(json_file)
        
        File.mtime(json_file) > File.mtime(xml_file)
      end
      
      def self.show_help
        puts <<~HELP
          Usage: kjui generate-xml [layout_name] [options]
          
          Generate Android XML layouts from JSON files
          
          Arguments:
            layout_name    Name of the layout to generate (optional)
                          If not specified, generates all layouts
          
          Options:
            -l, --layout <name>    Specify layout name
            -f, --force           Force regeneration even if up to date
            -h, --help            Show this help message
          
          Examples:
            kjui generate-xml                # Generate all layouts
            kjui generate-xml test_menu       # Generate specific layout
            kjui generate-xml -f              # Force regenerate all
            kjui generate-xml test_menu -f   # Force regenerate specific layout
        HELP
      end
    end
  end
end