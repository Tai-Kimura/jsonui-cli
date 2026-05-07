require 'digest'
require 'json'

module DrawableGenerator
  class DrawableHashManager
    HASH_REGISTRY_FILE = '.drawable_hashes.json'
    
    def initialize(drawable_dir)
      @drawable_dir = drawable_dir
      @registry_path = File.join(@drawable_dir, HASH_REGISTRY_FILE)
      @registry = load_registry
      @session_cache = {}
    end
    
    def generate_hash(content)
      # Generate a short hash from the content
      full_hash = Digest::SHA256.hexdigest(content)
      # Use first 8 characters for readability while maintaining uniqueness
      full_hash[0..7]
    end
    
    def drawable_exists?(drawable_name)
      # Check session cache first
      return true if @session_cache[drawable_name]
      
      # Check file system
      file_path = File.join(@drawable_dir, "#{drawable_name}.xml")
      exists = File.exist?(file_path)
      
      # Update cache if exists
      @session_cache[drawable_name] = true if exists
      
      exists
    end
    
    def register_drawable(drawable_name, content)
      # Add to session cache
      @session_cache[drawable_name] = true
      
      # Add to registry with metadata
      @registry[drawable_name] = {
        'hash' => generate_hash(content),
        'created_at' => Time.now.to_s,
        'content_hash' => Digest::MD5.hexdigest(content)
      }
      
      save_registry
    end
    
    def find_existing_drawable(content)
      content_hash = Digest::MD5.hexdigest(content)
      
      # Search registry for matching content
      @registry.each do |name, data|
        if data['content_hash'] == content_hash
          # Verify file still exists
          if drawable_exists?(name)
            return name
          else
            # Clean up orphaned registry entry
            @registry.delete(name)
          end
        end
      end
      
      nil
    end
    
    def cleanup_orphaned_drawables
      orphaned = []
      
      @registry.each do |name, _data|
        file_path = File.join(@drawable_dir, "#{name}.xml")
        unless File.exist?(file_path)
          orphaned << name
        end
      end
      
      orphaned.each { |name| @registry.delete(name) }
      save_registry if orphaned.any?
      
      orphaned
    end
    
    def list_drawables
      drawables = []
      
      Dir.glob(File.join(@drawable_dir, '*.xml')).each do |file|
        name = File.basename(file, '.xml')
        next if name == 'ic_launcher_foreground' # Skip system drawables
        next if name == 'ic_launcher_background'
        
        drawables << {
          name: name,
          path: file,
          size: File.size(file),
          modified: File.mtime(file)
        }
      end
      
      drawables.sort_by { |d| d[:name] }
    end
    
    def get_usage_stats
      stats = {
        total_drawables: 0,
        shape_drawables: 0,
        ripple_drawables: 0,
        selector_drawables: 0,
        total_size: 0,
        reuse_count: 0
      }
      
      list_drawables.each do |drawable|
        stats[:total_drawables] += 1
        stats[:total_size] += drawable[:size]
        
        case drawable[:name]
        when /^shape_/
          stats[:shape_drawables] += 1
        when /^ripple_/
          stats[:ripple_drawables] += 1
        when /^selector_/
          stats[:selector_drawables] += 1
        end
      end
      
      # Count reuses based on session cache
      stats[:reuse_count] = @session_cache.size
      
      stats
    end
    
    private
    
    def load_registry
      return {} unless File.exist?(@registry_path)
      
      begin
        JSON.parse(File.read(@registry_path))
      rescue JSON::ParserError
        {}
      end
    end
    
    def save_registry
      File.write(@registry_path, JSON.pretty_generate(@registry))
    rescue => e
      puts "Warning: Failed to save drawable registry: #{e.message}"
    end
  end
end