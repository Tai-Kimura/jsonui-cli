# frozen_string_literal: true

require 'json'
require 'fileutils'
require 'pathname'
require 'digest'

module KjuiTools
  module Compose
    class BuildCacheManager
      def initialize(source_path)
        @source_path = source_path
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
          styles_dir = File.join(@source_path, 'assets', 'Styles')
          style_dependencies[file_name].each do |style_file|
            style_path = File.join(styles_dir, "#{style_file}.json")
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
      
      def save_cache(including_files, style_dependencies)
        # Update last_updated with current timestamps
        last_updated = {}
        
        # Get all processed files
        all_files = (including_files.keys + style_dependencies.keys).uniq
        
        all_files.each do |file_name|
          layouts_dir = File.join(@source_path, 'assets', 'Layouts')
          json_file = File.join(layouts_dir, "#{file_name}.json")
          
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