# frozen_string_literal: true

require 'pathname'
require 'find'

module KjuiTools
  module Core
    class ProjectFinder
      class << self
        attr_accessor :project_dir, :project_file_path
        
        def setup_paths
          @project_dir = find_project_dir
          @project_file_path = find_project_file
        end
        
        def find_project_dir
          # Look for Android project indicators
          current_dir = Dir.pwd
          
          # Check current directory
          return current_dir if android_project?(current_dir)
          
          # Check parent directory
          parent_dir = File.dirname(current_dir)
          return parent_dir if android_project?(parent_dir)
          
          # Default to current directory
          current_dir
        end
        
        def find_project_file
          # Look for main build.gradle or build.gradle.kts
          gradle_files = Dir.glob('build.gradle*')
          return gradle_files.first if gradle_files.any?
          
          # Check parent directory
          parent_gradle = Dir.glob('../build.gradle*')
          return File.expand_path(parent_gradle.first) if parent_gradle.any?
          
          nil
        end
        
        def find_source_directory
          # Common Android source directory patterns
          common_paths = [
            'app/src/main',
            'src/main',
            'src',
            'app'
          ]
          
          project_root = @project_dir || Dir.pwd
          
          common_paths.each do |path|
            full_path = File.join(project_root, path)
            return path if Dir.exist?(full_path)
          end
          
          # Try to find any src directory
          Find.find(project_root) do |path|
            if File.directory?(path) && File.basename(path) == 'src'
              # Check if it contains main directory
              main_path = File.join(path, 'main')
              if Dir.exist?(main_path)
                return Pathname.new(main_path).relative_path_from(Pathname.new(project_root)).to_s
              end
              return Pathname.new(path).relative_path_from(Pathname.new(project_root)).to_s
            end
          end
          
          # Default
          'app/src/main'
        end
        
        def get_full_source_path
          @project_dir || Dir.pwd
        end
        
        def get_package_name
          package_name
        end
        
        def package_name
          # Try to detect package name from AndroidManifest.xml
          manifest_paths = [
            'app/src/main/AndroidManifest.xml',
            'src/main/AndroidManifest.xml',
            'AndroidManifest.xml'
          ]
          
          project_root = @project_dir || Dir.pwd
          
          manifest_paths.each do |path|
            full_path = File.join(project_root, path)
            if File.exist?(full_path)
              content = File.read(full_path)
              # Extract package name from manifest
              if content =~ /package="([^"]+)"/
                return $1
              end
            end
          end
          
          # Try to detect from build.gradle
          gradle_files = Dir.glob('**/build.gradle*')
          gradle_files.each do |gradle_file|
            content = File.read(gradle_file)
            # Look for namespace first (more reliable)
            if content =~ /namespace\s*=\s*["']([^"']+)["']/
              return $1
            end
            # Look for applicationId
            if content =~ /applicationId\s*=\s*["']([^"']+)["']/
              return $1
            end
          end
          
          # Default package name
          'com.example.app'
        end
        
        private
        
        def android_project?(dir)
          # Check for Android project indicators
          indicators = [
            'build.gradle',
            'build.gradle.kts',
            'settings.gradle',
            'settings.gradle.kts',
            'gradlew',
            'app/build.gradle',
            'app/build.gradle.kts'
          ]
          
          indicators.any? { |indicator| File.exist?(File.join(dir, indicator)) }
        end
      end
    end
  end
end