# frozen_string_literal: true

require 'fileutils'
require_relative '../../core/config_manager'
require_relative '../../core/frameworks'
require_relative '../../core/generated_marker'
require_relative '../../core/logger'

module RjuiTools
  module CLI
    module Commands
      class InitCommand
        def initialize(args)
          @args = args
        end

        def execute
          Core::Logger.info('Initializing ReactJsonUI...')

          # Create config file
          if File.exist?(Core::ConfigManager::CONFIG_FILE)
            Core::Logger.warn('Config file already exists, skipping...')
          else
            Core::ConfigManager.create_default_config
            Core::Logger.success("Created #{Core::ConfigManager::CONFIG_FILE}")
          end

          config = Core::ConfigManager.load_config

          # Create directories
          directories = [
            config['layouts_directory'],
            config['generated_directory'],
            config['components_directory'],
            config['styles_directory'],
            config['strings_directory']
          ]

          directories.each do |dir|
            if Dir.exist?(dir)
              Core::Logger.warn("Directory already exists: #{dir}")
            else
              FileUtils.mkdir_p(dir)
              Core::Logger.success("Created directory: #{dir}")
            end
          end

          # Create sample layout
          sample_layout_path = File.join(config['layouts_directory'], 'sample.json')
          unless File.exist?(sample_layout_path)
            create_sample_layout(sample_layout_path)
            Core::Logger.success("Created sample layout: #{sample_layout_path}")
          end

          # Create language files
          create_language_files(config)

          # Create StringManager
          create_string_manager(config)

          # Create built-in components
          create_builtin_components(config)

          Core::Logger.success('ReactJsonUI initialized successfully!')
          Core::Logger.info('Run "rjui build" to generate React components')
        end

        private

        def create_sample_layout(path)
          sample = {
            'type' => 'View',
            'id' => 'sample_container',
            'className' => 'p-4',
            'child' => [
              {
                'type' => 'Label',
                'id' => 'title',
                'text' => 'Hello ReactJsonUI!',
                'fontSize' => 24,
                'fontColor' => '#000000'
              },
              {
                'type' => 'Button',
                'id' => 'action_button',
                'text' => 'Click Me',
                'onClick' => 'handleClick',
                'background' => '#007AFF',
                'fontColor' => '#FFFFFF',
                'cornerRadius' => 8,
                'padding' => [12, 24]
              }
            ]
          }

          File.write(path, JSON.pretty_generate(sample))
        end

        def create_language_files(config)
          strings_dir = config['strings_directory'] || 'src/Strings'
          languages = config['languages'] || ['en', 'ja']

          languages.each do |lang|
            lang_file = File.join(strings_dir, "#{lang}.json")
            next if File.exist?(lang_file)

            # Create sample strings for each language
            sample_strings = case lang
                             when 'en'
                               {
                                 'app_name' => 'My App',
                                 'welcome_message' => 'Welcome!',
                                 'button_submit' => 'Submit',
                                 'button_cancel' => 'Cancel'
                               }
                             when 'ja'
                               {
                                 'app_name' => 'マイアプリ',
                                 'welcome_message' => 'ようこそ！',
                                 'button_submit' => '送信',
                                 'button_cancel' => 'キャンセル'
                               }
                             else
                               {
                                 'app_name' => 'My App',
                                 'welcome_message' => 'Welcome!'
                               }
                             end

            File.write(lang_file, JSON.pretty_generate(sample_strings))
            Core::Logger.success("Created language file: #{lang_file}")
          end
        end

        def create_string_manager(config)
          generated_dir = config['generated_directory'] || 'src/generated'
          is_ts = config['typescript']
          extension = is_ts ? 'ts' : 'js'
          string_manager_path = File.join(generated_dir, "StringManager.#{extension}")

          # Only skip when the correct-extension file exists. If the other
          # extension is lingering from a mode flip, wipe it so imports don't
          # resolve twice.
          other_path = File.join(generated_dir, "StringManager.#{is_ts ? 'js' : 'ts'}")
          File.delete(other_path) if File.exist?(other_path)
          return if File.exist?(string_manager_path)

          languages = config['languages'] || ['en', 'ja']
          default_language = config['default_language'] || 'en'
          strings_dir = config['strings_directory'] || 'src/Strings'

          # Read string files and embed them directly
          strings_data = {}
          languages.each do |lang|
            lang_file = File.join(strings_dir, "#{lang}.json")
            if File.exist?(lang_file)
              strings_data[lang] = JSON.parse(File.read(lang_file, encoding: 'UTF-8'))
            else
              strings_data[lang] = {}
            end
          end

          # Generate embedded strings object
          strings_json = JSON.pretty_generate(strings_data)
          marker_header = Core::GeneratedMarker.comment_header(
            source: "StringManager (strings from Strings/*.json)",
            generator: "rjui init"
          )
          marker_footer = Core::GeneratedMarker.comment_footer

          content = if is_ts
                      string_manager_typescript_stub(strings_json, default_language, marker_header, marker_footer)
                    else
                      string_manager_javascript_stub(strings_json, default_language, marker_header, marker_footer)
                    end

          File.write(string_manager_path, content)
          Core::Logger.success("Created StringManager: #{string_manager_path}")
        end

        def string_manager_javascript_stub(strings_json, default_language, marker_header, marker_footer)
          fw = Core::Frameworks.for(Core::ConfigManager.load_config)
          <<~JS
            #{fw.use_client_prefix}#{marker_header}
            // Manages multi-language string resources.

            import { useSyncExternalStore } from 'react';

            const strings = #{strings_json};

            const LANGUAGE_STORAGE_KEY = 'jsonui-language';
            const LANGUAGE_EVENT = 'jsonui:languagechange';

            // Convert snake_case keys to camelCase for property access
            function createCamelCaseProxy(obj) {
              const camelCaseMap = {};
              for (const key in obj) {
                const camelKey = key.replace(/_([a-z0-9])/g, (_, letter) => letter.toUpperCase());
                camelCaseMap[camelKey] = obj[key];
                camelCaseMap[key] = obj[key]; // Also keep snake_case access
              }
              return camelCaseMap;
            }

            class StringManagerClass {
              constructor() {
                this._currentLanguage = '#{default_language}';
                if (typeof window !== 'undefined') {
                  const saved = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
                  if (saved && strings[saved]) {
                    this._currentLanguage = saved;
                  }
                }
                this._cache = {};
              }

              get currentLanguage() {
                const lang = this._currentLanguage;
                if (!this._cache[lang]) {
                  this._cache[lang] = createCamelCaseProxy(strings[lang] || strings['#{default_language}']);
                }
                return this._cache[lang];
              }

              get language() {
                return this._currentLanguage;
              }

              setLanguage(lang) {
                if (!strings[lang]) {
                  console.warn(`Language '${lang}' not found. Available: ${Object.keys(strings).join(', ')}`);
                  return;
                }
                if (this._currentLanguage === lang) return;
                this._currentLanguage = lang;
                this._cache = {};
                if (typeof window !== 'undefined') {
                  window.localStorage.setItem(LANGUAGE_STORAGE_KEY, lang);
                  window.dispatchEvent(new CustomEvent(LANGUAGE_EVENT, { detail: { language: lang } }));
                }
              }

              get availableLanguages() {
                return Object.keys(strings);
              }

              getString(key) {
                return this.currentLanguage[key] || key;
              }

              // SSR-safe lookup pinned to the default language. Use this from
              // ViewModel constructors / onAppear / any code path that runs
              // during SSR or before hydration; getString(key) reads
              // currentLanguage which may diverge between server and client
              // when the user has a persisted locale, causing hydration
              // mismatches. Re-seed with getString from a post-mount hook
              // (e.g. useEffect) once the client has hydrated.
              getDefaultString(key) {
                const defaultLang = '#{default_language}';
                if (!this._cache[defaultLang]) {
                  this._cache[defaultLang] = createCamelCaseProxy(strings[defaultLang]);
                }
                return this._cache[defaultLang][key] || key;
              }
            }

            export const StringManager = new StringManagerClass();
            export default StringManager;

            // Reactive hook — generated components consume this as `const $s = useStringManager()`.
            // Subscribes to `setLanguage` events so every call site re-renders on language change.
            function subscribeLanguage(callback) {
              if (typeof window === 'undefined') return () => {};
              window.addEventListener(LANGUAGE_EVENT, callback);
              return () => window.removeEventListener(LANGUAGE_EVENT, callback);
            }

            function getLanguageSnapshot() {
              return StringManager.currentLanguage;
            }

            // SSR + client first render must agree, otherwise React reports a
            // hydration mismatch when the persisted locale differs from the
            // default. Keep the server snapshot fixed to the default-language
            // proxy; the post-hydration subscribe pass swaps in the real
            // persisted locale via getLanguageSnapshot.
            let _serverSnapshot = null;
            function getServerSnapshot() {
              if (!_serverSnapshot) {
                _serverSnapshot = createCamelCaseProxy(strings['#{default_language}']);
              }
              return _serverSnapshot;
            }

            export function useStringManager() {
              return useSyncExternalStore(subscribeLanguage, getLanguageSnapshot, getServerSnapshot);
            }

            #{marker_footer}
          JS
        end

        def string_manager_typescript_stub(strings_json, default_language, marker_header, marker_footer)
          fw = Core::Frameworks.for(Core::ConfigManager.load_config)
          <<~TS
            #{fw.use_client_prefix}#{marker_header}
            // Manages multi-language string resources.

            import { useSyncExternalStore } from 'react';

            type StringMap = Record<string, string>;
            type StringsRoot = Record<string, StringMap>;

            const strings: StringsRoot = #{strings_json};

            const LANGUAGE_STORAGE_KEY = 'jsonui-language';
            const LANGUAGE_EVENT = 'jsonui:languagechange';

            function createCamelCaseProxy(obj: StringMap): StringMap {
              const camelCaseMap: StringMap = {};
              for (const key in obj) {
                const camelKey = key.replace(/_([a-z0-9])/g, (_, letter) => letter.toUpperCase());
                camelCaseMap[camelKey] = obj[key];
                camelCaseMap[key] = obj[key];
              }
              return camelCaseMap;
            }

            class StringManagerClass {
              private _currentLanguage: string;
              private _cache: Record<string, StringMap>;

              constructor() {
                this._currentLanguage = '#{default_language}';
                if (typeof window !== 'undefined') {
                  const saved = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
                  if (saved && strings[saved]) {
                    this._currentLanguage = saved;
                  }
                }
                this._cache = {};
              }

              get currentLanguage(): StringMap {
                const lang = this._currentLanguage;
                if (!this._cache[lang]) {
                  this._cache[lang] = createCamelCaseProxy(strings[lang] || strings['#{default_language}']);
                }
                return this._cache[lang];
              }

              get language(): string {
                return this._currentLanguage;
              }

              setLanguage(lang: string): void {
                if (!strings[lang]) {
                  console.warn(`Language '${lang}' not found. Available: ${Object.keys(strings).join(', ')}`);
                  return;
                }
                if (this._currentLanguage === lang) return;
                this._currentLanguage = lang;
                this._cache = {};
                if (typeof window !== 'undefined') {
                  window.localStorage.setItem(LANGUAGE_STORAGE_KEY, lang);
                  window.dispatchEvent(new CustomEvent(LANGUAGE_EVENT, { detail: { language: lang } }));
                }
              }

              get availableLanguages(): string[] {
                return Object.keys(strings);
              }

              getString(key: string): string {
                return this.currentLanguage[key] || key;
              }

              // SSR-safe lookup pinned to the default language. Use this from
              // ViewModel constructors / onAppear / any code path that runs
              // during SSR or before hydration; getString(key) reads
              // currentLanguage which may diverge between server and client
              // when the user has a persisted locale, causing hydration
              // mismatches. Re-seed with getString from a post-mount hook
              // (e.g. useEffect) once the client has hydrated.
              getDefaultString(key: string): string {
                const defaultLang = '#{default_language}';
                if (!this._cache[defaultLang]) {
                  this._cache[defaultLang] = createCamelCaseProxy(strings[defaultLang]);
                }
                return this._cache[defaultLang][key] || key;
              }
            }

            export const StringManager = new StringManagerClass();
            export default StringManager;

            // Reactive hook — generated components consume this as `const $s = useStringManager()`.
            // Subscribes to `setLanguage` events so every call site re-renders on language change.
            function subscribeLanguage(callback: () => void): () => void {
              if (typeof window === 'undefined') return () => {};
              window.addEventListener(LANGUAGE_EVENT, callback);
              return () => window.removeEventListener(LANGUAGE_EVENT, callback);
            }

            function getLanguageSnapshot(): StringMap {
              return StringManager.currentLanguage;
            }

            // SSR + client first render must agree, otherwise React reports a
            // hydration mismatch when the persisted locale differs from the
            // default. Keep the server snapshot fixed to the default-language
            // proxy; the post-hydration subscribe pass swaps in the real
            // persisted locale via getLanguageSnapshot.
            let _serverSnapshot: StringMap | null = null;
            function getServerSnapshot(): StringMap {
              if (!_serverSnapshot) {
                _serverSnapshot = createCamelCaseProxy(strings['#{default_language}']);
              }
              return _serverSnapshot;
            }

            export function useStringManager(): StringMap {
              return useSyncExternalStore(subscribeLanguage, getLanguageSnapshot, getServerSnapshot);
            }

            #{marker_footer}
          TS
        end

        def create_builtin_components(config)
          extensions_dir = config['extensions_directory'] || 'src/components/extensions'
          FileUtils.mkdir_p(extensions_dir)

          # Create NetworkImage component
          network_image_path = File.join(extensions_dir, 'NetworkImage.tsx')
          unless File.exist?(network_image_path)
            template_path = File.join(File.dirname(__FILE__), '../../react/templates/network_image.tsx')
            fw = Core::Frameworks.for(config)
            File.write(network_image_path, Core::Frameworks.apply_directive(File.read(template_path), fw))
            Core::Logger.success("Created built-in component: #{network_image_path}")
          end

          # Create EmbedContainer component (Embed view type runtime helper)
          embed_container_path = File.join(extensions_dir, 'EmbedContainer.tsx')
          unless File.exist?(embed_container_path)
            template_path = File.join(File.dirname(__FILE__), '../../react/templates/EmbedContainer.tsx')
            File.write(embed_container_path, File.read(template_path))
            Core::Logger.success("Created built-in component: #{embed_container_path}")
          end

          # Create LinkifyText component (Label `linkable` runtime)
          linkify_text_path = File.join(extensions_dir, 'LinkifyText.tsx')
          unless File.exist?(linkify_text_path)
            template_path = File.join(File.dirname(__FILE__), '../../react/templates/linkify_text.tsx')
            fw = Core::Frameworks.for(config)
            File.write(linkify_text_path, Core::Frameworks.apply_directive(File.read(template_path), fw))
            Core::Logger.success("Created built-in component: #{linkify_text_path}")
          end

          # Create Configuration template (FontSpec / Configuration.Font.fontProvider)
          # so generated components can `import { Configuration } from '@/lib/jsonui/Configuration'`.
          lib_dir = config['lib_directory'] || 'src/lib/jsonui'
          FileUtils.mkdir_p(lib_dir)
          configuration_path = File.join(lib_dir, 'Configuration.ts')
          unless File.exist?(configuration_path)
            template_path = File.join(File.dirname(__FILE__), '../../react/templates/Configuration.ts')
            if File.exist?(template_path)
              File.write(configuration_path, File.read(template_path))
              Core::Logger.success("Created Configuration template: #{configuration_path}")
            end
          end
        end
      end
    end
  end
end
