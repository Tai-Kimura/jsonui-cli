#!/usr/bin/env ruby

require 'fileutils'
require 'json'
require_relative '../../core/config_manager'
require_relative '../../core/project_finder'

module KjuiTools
  module Xml
    module Generators
      class ViewGenerator
        def initialize(name, options = {})
          @name = name
          @options = options
          @config = Core::ConfigManager.load_config
          @project_path = @config['project_path'] || Dir.pwd
          @package_name = @config['package_name'] || detect_package_name
          
          # Determine view type (activity or fragment)
          @view_type = options[:type] || 'activity'
          @is_activity = @view_type == 'activity'
          
          # Setup paths
          setup_paths
        end

        def generate
          puts "📱 Generating XML view: #{@name}"
          puts "   Type: #{@view_type.capitalize}"
          puts "   Package: #{@package_name}"
          
          # Generate all components
          generate_json_layout
          generate_xml_layout
          generate_data_class
          generate_view_model
          generate_view_class
          
          puts "✅ Successfully generated XML view: #{@name}"
          puts ""
          puts "Generated files:"
          puts "  📄 #{@json_file}"
          puts "  📄 #{@xml_file}"
          puts "  📄 #{@data_file}"
          puts "  📄 #{@viewmodel_file}"
          puts "  📄 #{@view_file}"
        end

        private

        def setup_paths
          # JSON layout path
          @layouts_dir = File.join(@project_path, 'src', 'main', 'assets', 'Layouts')
          FileUtils.mkdir_p(@layouts_dir)
          @json_file = File.join(@layouts_dir, "#{snake_case(@name)}.json")
          
          # XML layout path
          @res_layout_dir = File.join(@project_path, 'src', 'main', 'res', 'layout')
          FileUtils.mkdir_p(@res_layout_dir)
          
          # Determine XML file name based on type
          xml_suffix = @is_activity ? '_activity' : '_fragment'
          @xml_file = File.join(@res_layout_dir, "#{snake_case(@name)}#{xml_suffix}.xml")
          
          # Kotlin source paths
          base_kotlin_path = File.join(@project_path, 'src', 'main', 'kotlin')
          package_path = @package_name.gsub('.', '/')
          
          # Data class path
          @data_dir = File.join(base_kotlin_path, package_path, 'data')
          FileUtils.mkdir_p(@data_dir)
          @data_file = File.join(@data_dir, "#{pascal_case(@name)}Data.kt")
          
          # ViewModel path
          @viewmodel_dir = File.join(base_kotlin_path, package_path, 'viewmodels')
          FileUtils.mkdir_p(@viewmodel_dir)
          @viewmodel_file = File.join(@viewmodel_dir, "#{pascal_case(@name)}ViewModel.kt")
          
          # View (Activity/Fragment) path
          view_subdir = @is_activity ? 'activities' : 'fragments'
          @view_dir = File.join(base_kotlin_path, package_path, view_subdir)
          FileUtils.mkdir_p(@view_dir)
          @view_file = File.join(@view_dir, "#{pascal_case(@name)}#{@view_type.capitalize}.kt")
        end

        def detect_package_name
          # Try AndroidManifest.xml
          manifest_paths = [
            File.join(@project_path, 'src', 'main', 'AndroidManifest.xml'),
            File.join(@project_path, 'app', 'src', 'main', 'AndroidManifest.xml')
          ]
          
          manifest_paths.each do |path|
            if File.exist?(path)
              content = File.read(path)
              if content =~ /package="([^"]+)"/
                return $1
              end
            end
          end
          
          # Try build.gradle
          gradle_files = Dir.glob(File.join(@project_path, '**', 'build.gradle*'))
          gradle_files.each do |file|
            content = File.read(file)
            if content =~ /namespace\s*[=:]\s*["']([^"']+)["']/
              return $1
            elsif content =~ /applicationId\s*[=:]\s*["']([^"']+)["']/
              return $1
            end
          end
          
          'com.example.app'
        end

        def generate_json_layout
          return if File.exist?(@json_file) && !@options[:force]
          
          content = {
            type: "View",
            width: "matchParent",
            height: "matchParent",
            orientation: "vertical",
            padding: 16,
            background: "#FFFFFF",
            child: [
              {
                type: "Label",
                id: "titleText",
                text: "@{title}",
                fontSize: 24,
                fontWeight: "bold",
                fontColor: "#333333",
                bottomMargin: 16
              },
              {
                type: "Label",
                id: "messageText",
                text: "@{message}",
                fontSize: 16,
                fontColor: "#666666",
                bottomMargin: 24
              },
              {
                type: "Button",
                id: "actionButton",
                text: "Click Me",
                onClick: "@{viewModel.onButtonClick()}",
                background: "#007AFF",
                fontColor: "#FFFFFF",
                padding: 12,
                cornerRadius: 8
              }
            ],
            data: {
              title: "Welcome",
              message: "This is #{@name} view"
            }
          }
          
          File.write(@json_file, JSON.pretty_generate(content))
          puts "   Created JSON layout: #{@json_file}"
        end

        def generate_xml_layout
          # Use the XML generator to create the layout from JSON
          require_relative '../xml_generator'
          
          config = @config.merge({
            'project_path' => @project_path,
            'package_name' => @package_name
          })
          
          # Determine the output filename
          xml_suffix = @is_activity ? '_activity' : '_fragment'
          output_filename = "#{snake_case(@name)}#{xml_suffix}.xml"
          
          generator = XmlGenerator::Generator.new(
            snake_case(@name), 
            config,
            { output_filename: output_filename }
          )
          generator.generate
        end

        def generate_data_class
          return if File.exist?(@data_file) && !@options[:force]
          
          content = <<~KOTLIN
          package #{@package_name}.data

          data class #{pascal_case(@name)}Data(
              val title: String = "Welcome",
              val message: String = "This is #{@name} view"
          )
          KOTLIN
          
          File.write(@data_file, content)
          puts "   Created data class: #{@data_file}"
        end

        def generate_view_model
          return if File.exist?(@viewmodel_file) && !@options[:force]
          
          content = <<~KOTLIN
          package #{@package_name}.viewmodels

          import androidx.lifecycle.ViewModel
          import androidx.lifecycle.MutableLiveData
          import androidx.lifecycle.LiveData
          import #{@package_name}.data.#{pascal_case(@name)}Data

          class #{pascal_case(@name)}ViewModel : ViewModel() {
              private val _data = MutableLiveData<#{pascal_case(@name)}Data>()
              val data: LiveData<#{pascal_case(@name)}Data> = _data

              init {
                  _data.value = #{pascal_case(@name)}Data()
              }

              fun onButtonClick() {
                  // Handle button click
                  updateData(
                      _data.value?.copy(
                          message = "Button clicked at \${System.currentTimeMillis()}"
                      ) ?: #{pascal_case(@name)}Data()
                  )
              }

              fun updateData(newData: #{pascal_case(@name)}Data) {
                  _data.value = newData
              }
          }
          KOTLIN
          
          File.write(@viewmodel_file, content)
          puts "   Created ViewModel: #{@viewmodel_file}"
        end

        def generate_view_class
          return if File.exist?(@view_file) && !@options[:force]
          
          if @is_activity
            generate_activity
          else
            generate_fragment
          end
        end

        def generate_activity
          content = <<~KOTLIN
          package #{@package_name}.activities

          import android.os.Bundle
          import androidx.appcompat.app.AppCompatActivity
          import androidx.databinding.DataBindingUtil
          import androidx.lifecycle.ViewModelProvider
          import #{@package_name}.R
          import #{@package_name}.databinding.#{pascal_case(@name)}ActivityBinding
          import #{@package_name}.viewmodels.#{pascal_case(@name)}ViewModel

          class #{pascal_case(@name)}Activity : AppCompatActivity() {
              private lateinit var binding: #{pascal_case(@name)}ActivityBinding
              private lateinit var viewModel: #{pascal_case(@name)}ViewModel

              override fun onCreate(savedInstanceState: Bundle?) {
                  super.onCreate(savedInstanceState)
                  
                  // Initialize data binding
                  binding = DataBindingUtil.setContentView(this, R.layout.#{snake_case(@name)}_activity)
                  
                  // Initialize ViewModel
                  viewModel = ViewModelProvider(this).get(#{pascal_case(@name)}ViewModel::class.java)
                  
                  // Set binding variables
                  binding.lifecycleOwner = this
                  binding.viewModel = viewModel
                  
                  // Observe data changes
                  viewModel.data.observe(this) { data ->
                      binding.data = data
                  }
              }
          }
          KOTLIN
          
          File.write(@view_file, content)
          puts "   Created Activity: #{@view_file}"
        end

        def generate_fragment
          content = <<~KOTLIN
          package #{@package_name}.fragments

          import android.os.Bundle
          import android.view.LayoutInflater
          import android.view.View
          import android.view.ViewGroup
          import androidx.fragment.app.Fragment
          import androidx.databinding.DataBindingUtil
          import androidx.lifecycle.ViewModelProvider
          import #{@package_name}.R
          import #{@package_name}.databinding.#{pascal_case(@name)}FragmentBinding
          import #{@package_name}.viewmodels.#{pascal_case(@name)}ViewModel

          class #{pascal_case(@name)}Fragment : Fragment() {
              private lateinit var binding: #{pascal_case(@name)}FragmentBinding
              private lateinit var viewModel: #{pascal_case(@name)}ViewModel

              override fun onCreateView(
                  inflater: LayoutInflater,
                  container: ViewGroup?,
                  savedInstanceState: Bundle?
              ): View {
                  // Initialize data binding
                  binding = DataBindingUtil.inflate(
                      inflater,
                      R.layout.#{snake_case(@name)}_fragment,
                      container,
                      false
                  )
                  
                  return binding.root
              }

              override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
                  super.onViewCreated(view, savedInstanceState)
                  
                  // Initialize ViewModel
                  viewModel = ViewModelProvider(this).get(#{pascal_case(@name)}ViewModel::class.java)
                  
                  // Set binding variables
                  binding.lifecycleOwner = viewLifecycleOwner
                  binding.viewModel = viewModel
                  
                  // Observe data changes
                  viewModel.data.observe(viewLifecycleOwner) { data ->
                      binding.data = data
                  }
              }
          }
          KOTLIN
          
          File.write(@view_file, content)
          puts "   Created Fragment: #{@view_file}"
        end

        def snake_case(str)
          str.gsub(/([A-Z]+)([A-Z][a-z])/, '\1_\2')
             .gsub(/([a-z\d])([A-Z])/, '\1_\2')
             .downcase
        end

        def pascal_case(str)
          # If already in PascalCase (starts with capital and has mixed case), return as is
          return str if str =~ /^[A-Z]/ && str =~ /[a-z]/
          
          # Convert from snake_case or kebab-case to PascalCase
          str.split(/[_\s-]/).map do |word|
            word[0].upcase + word[1..-1].downcase
          end.join
        end
      end
    end
  end
end