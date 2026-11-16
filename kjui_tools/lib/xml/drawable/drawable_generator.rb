require 'digest'
require 'fileutils'
require_relative 'shape_drawable_generator'
require_relative 'ripple_drawable_generator'
require_relative 'state_list_drawable_generator'
require_relative 'drawable_hash_manager'

module DrawableGenerator
  class Generator
    def initialize(project_root)
      @project_root = project_root
      
      # Check if we're already in a sample-app directory or need to look for one
      if File.exist?(File.join(project_root, 'src', 'main', 'res'))
        @drawable_dir = File.join(project_root, 'src', 'main', 'res', 'drawable')
      elsif File.exist?(File.join(project_root, 'sample-app', 'src', 'main', 'res'))
        @drawable_dir = File.join(project_root, 'sample-app', 'src', 'main', 'res', 'drawable')
      elsif File.exist?(File.join(project_root, 'app', 'src', 'main', 'res'))
        @drawable_dir = File.join(project_root, 'app', 'src', 'main', 'res', 'drawable')
      else
        # Default fallback
        @drawable_dir = File.join(project_root, 'src', 'main', 'res', 'drawable')
      end
      
      @hash_manager = DrawableHashManager.new(@drawable_dir)
      @shape_generator = ShapeDrawableGenerator.new
      @ripple_generator = RippleDrawableGenerator.new
      @state_list_generator = StateListDrawableGenerator.new
      
      ensure_drawable_directory
    end
    
    def generate_for_component(json_data, component_type)
      drawables = []
      
      # Check if we need a ripple effect drawable
      if needs_ripple?(json_data, component_type)
        drawable_name = generate_ripple_drawable(json_data, component_type)
        drawables << drawable_name if drawable_name
      end
      
      # Check if we need a shape drawable
      if needs_shape?(json_data)
        drawable_name = generate_shape_drawable(json_data, component_type)
        drawables << drawable_name if drawable_name
      end
      
      # Check if we need a state list drawable
      if needs_state_list?(json_data)
        drawable_name = generate_state_list_drawable(json_data, component_type)
        drawables << drawable_name if drawable_name
      end
      
      drawables.first # Return the primary drawable (usually state list or ripple)
    end
    
    def get_background_drawable(json_data, component_type)
      return nil unless json_data
      
      # Priority order: state list > ripple > shape > color
      if needs_state_list?(json_data)
        generate_state_list_drawable(json_data, component_type)
      elsif needs_ripple?(json_data, component_type)
        generate_ripple_drawable(json_data, component_type)
      elsif needs_shape?(json_data)
        generate_shape_drawable(json_data, component_type)
      else
        nil
      end
    end
    
    private
    
    def ensure_drawable_directory
      FileUtils.mkdir_p(@drawable_dir) unless Dir.exist?(@drawable_dir)
    end
    
    def needs_ripple?(json_data, component_type)
      return false unless json_data
      
      # Check for click handlers
      has_click_handler = json_data['onClick'] || json_data['onclick']
      
      # Certain component types should have ripple by default
      clickable_components = ['Button', 'ImageButton', 'Card', 'ListItem']
      is_clickable_component = clickable_components.include?(component_type)
      
      has_click_handler || is_clickable_component
    end
    
    def needs_shape?(json_data)
      return false unless json_data
      
      # Check for shape-related attributes
      json_data['cornerRadius'] || 
      json_data['borderWidth'] || 
      json_data['borderColor'] ||
      json_data['background']&.start_with?('#') ||
      json_data['gradient']
    end
    
    def needs_state_list?(json_data)
      return false unless json_data
      
      # Check for state-specific attributes
      json_data['disabledBackground'] ||
      json_data['tapBackground'] ||
      json_data['selectedBackground'] ||
      json_data['pressedBackground'] ||
      json_data['focusedBackground']
    end
    
    def generate_ripple_drawable(json_data, component_type)
      # Generate content based on attributes
      drawable_content = @ripple_generator.generate(json_data, component_type)
      return nil unless drawable_content
      
      # Generate hash-based filename
      drawable_hash = @hash_manager.generate_hash(drawable_content)
      drawable_name = "ripple_#{drawable_hash}"
      
      # Check if drawable already exists
      if @hash_manager.drawable_exists?(drawable_name)
        return drawable_name
      end
      
      # Write the drawable file
      drawable_path = File.join(@drawable_dir, "#{drawable_name}.xml")
      File.write(drawable_path, drawable_content)
      @hash_manager.register_drawable(drawable_name, drawable_content)
      
      drawable_name
    end
    
    def generate_shape_drawable(json_data, component_type)
      # Generate content based on attributes
      drawable_content = @shape_generator.generate(json_data)
      return nil unless drawable_content
      
      # Generate hash-based filename
      drawable_hash = @hash_manager.generate_hash(drawable_content)
      drawable_name = "shape_#{drawable_hash}"
      
      # Check if drawable already exists
      if @hash_manager.drawable_exists?(drawable_name)
        return drawable_name
      end
      
      # Write the drawable file
      drawable_path = File.join(@drawable_dir, "#{drawable_name}.xml")
      File.write(drawable_path, drawable_content)
      @hash_manager.register_drawable(drawable_name, drawable_content)
      
      drawable_name
    end
    
    def generate_state_list_drawable(json_data, component_type)
      # Generate content based on attributes
      drawable_content = @state_list_generator.generate(json_data, self)
      return nil unless drawable_content
      
      # Generate hash-based filename
      drawable_hash = @hash_manager.generate_hash(drawable_content)
      drawable_name = "selector_#{drawable_hash}"
      
      # Check if drawable already exists
      if @hash_manager.drawable_exists?(drawable_name)
        return drawable_name
      end
      
      # Write the drawable file
      drawable_path = File.join(@drawable_dir, "#{drawable_name}.xml")
      File.write(drawable_path, drawable_content)
      @hash_manager.register_drawable(drawable_name, drawable_content)
      
      drawable_name
    end
    
    # Public method for state list generator to create sub-drawables
    def create_shape_drawable_for_state(state_data)
      return nil unless state_data
      generate_shape_drawable(state_data, nil)
    end
  end
end