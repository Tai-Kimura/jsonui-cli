# frozen_string_literal: true

require 'json'
require 'fileutils'
require 'pathname'
require 'digest'

module KjuiTools
  module Compose
    class BuildCacheManager
      # `layouts_dir` / `styles_dir` come from the caller, which is the only
      # place that knows them: build.rb resolves
      # `<source_path>/<source_directory>/<layouts_directory>`, while this
      # class used to rebuild the path as `<source_path>/assets/Layouts`.
      # With a stock `source_directory` of `app/src/main` those are different
      # directories, `File.exist?` was false for every layout, and
      # `last_updated.json` stayed `{}` — the mtime cache was never written,
      # so nothing was ever cached (measured: 12 consecutive builds, "all
      # cached" 0 times).
      #
      # The old hard-coded paths remain as the fallback so an existing caller
      # that passes only `source_path` behaves exactly as before.
      def initialize(source_path, layouts_dir: nil, styles_dir: nil)
        @source_path = source_path
        @layouts_dir = layouts_dir || File.join(source_path, 'assets', 'Layouts')
        @styles_dir = styles_dir || File.join(source_path, 'assets', 'Styles')
        @cache_dir = File.join(source_path, '.kjui_cache')
        @last_updated_file = File.join(@cache_dir, 'last_updated.json')
        @including_files_cache = File.join(@cache_dir, 'including_files.json')
        @style_dependencies_cache = File.join(@cache_dir, 'style_dependencies.json')
        
        # Create cache directory if it doesn't exist
        FileUtils.mkdir_p(@cache_dir) unless File.exist?(@cache_dir)
      end
      
      def load_last_updated
        return {} unless File.exist?(@last_updated_file)
        JSON.parse(File.read(@last_updated_file))
      rescue JSON::ParserError
        {}
      end
      
      def load_last_including_files
        return {} unless File.exist?(@including_files_cache)
        JSON.parse(File.read(@including_files_cache))
      rescue JSON::ParserError
        {}
      end
      
      def load_style_dependencies
        return {} unless File.exist?(@style_dependencies_cache)
        JSON.parse(File.read(@style_dependencies_cache))
      rescue JSON::ParserError
        {}
      end
      
      def needs_update?(json_file, last_updated, layouts_dir, last_including_files, style_dependencies)
        file_name = File.basename(json_file, '.json')
        
        # Check if file exists in last_updated
        return true unless last_updated[file_name]
        
        # Check if file has been modified
        file_mtime = File.mtime(json_file).to_i
        return true if file_mtime > last_updated[file_name]['mtime'].to_i
        
        # Check if any included files have been modified
        if last_including_files[file_name]
          last_including_files[file_name].each do |included_file|
            included_path = File.join(layouts_dir, "#{included_file}.json")
            if File.exist?(included_path)
              included_mtime = File.mtime(included_path).to_i
              return true if included_mtime > last_updated[file_name]['mtime'].to_i
            end
          end
        end
        
        # Check if any style dependencies have been modified
        if style_dependencies[file_name]
          style_dependencies[file_name].each do |style_file|
            style_path = File.join(@styles_dir, "#{style_file}.json")
            if File.exist?(style_path)
              style_mtime = File.mtime(style_path).to_i
              return true if style_mtime > last_updated[file_name]['mtime'].to_i
            end
          end
        end
        
        # Check if any file that includes this file has been modified
        last_including_files.each do |parent_file, includes|
          if includes && includes.include?(file_name)
            parent_path = File.join(layouts_dir, "#{parent_file}.json")
            if File.exist?(parent_path)
              parent_mtime = File.mtime(parent_path).to_i
              return true if parent_mtime > last_updated[file_name]['mtime'].to_i
            end
          end
        end
        
        false
      end
      
      def extract_includes(json_data, includes = Set.new)
        if json_data.is_a?(Hash)
          # Check for include
          if json_data['include']
            includes.add(json_data['include'])
          end
          
          # Process children
          if json_data['child']
            if json_data['child'].is_a?(Array)
              json_data['child'].each do |child|
                extract_includes(child, includes)
              end
            else
              extract_includes(json_data['child'], includes)
            end
          end
        elsif json_data.is_a?(Array)
          json_data.each do |item|
            extract_includes(item, includes)
          end
        end
        
        includes.to_a
      end
      
      def extract_styles(json_data, styles = Set.new)
        if json_data.is_a?(Hash)
          # Check for style attribute
          if json_data['style']
            styles.add(json_data['style'])
          end
          
          # Process children
          if json_data['child']
            if json_data['child'].is_a?(Array)
              json_data['child'].each do |child|
                extract_styles(child, styles)
              end
            else
              extract_styles(json_data['child'], styles)
            end
          end
        elsif json_data.is_a?(Array)
          json_data.each do |item|
            extract_styles(item, styles)
          end
        end
        
        styles.to_a
      end
      
      def save_cache(including_files, style_dependencies, layout_names = nil)
        # Update last_updated with current timestamps
        last_updated = {}
        
        # Every layout the build processed — not only the ones that happen to
        # have includes or styles. Keyed on those two maps alone, a plain
        # layout was never recorded and so was dirty on every run.
        all_files = (including_files.keys + style_dependencies.keys + Array(layout_names)).uniq

        all_files.each do |file_name|
          json_file = File.join(@layouts_dir, "#{file_name}.json")
          
          if File.exist?(json_file)
            last_updated[file_name] = {
              'mtime' => File.mtime(json_file).to_i,
              'hash' => Digest::MD5.hexdigest(File.read(json_file))
            }
          end
        end
        
        # Save all cache files
        File.write(@last_updated_file, JSON.pretty_generate(last_updated))
        File.write(@including_files_cache, JSON.pretty_generate(including_files))
        File.write(@style_dependencies_cache, JSON.pretty_generate(style_dependencies))
      end
      
      def clean_cache
        FileUtils.rm_rf(@cache_dir)
        FileUtils.mkdir_p(@cache_dir)
      end
    end
  end
end