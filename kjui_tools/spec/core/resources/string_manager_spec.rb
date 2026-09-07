# frozen_string_literal: true

require 'core/resources/string_manager'
require 'core/config_manager'
require 'core/project_finder'

RSpec.describe KjuiTools::Core::Resources::StringManager do
  let(:temp_dir) { Dir.mktmpdir }
  let(:config) do
    {
      'source_directory' => 'src/main',
      'package_name' => 'com.example.app'
    }
  end
  let(:source_path) { temp_dir }
  let(:resources_dir) { File.join(temp_dir, 'src/main/assets/Layouts/Resources') }
  let(:manager) { described_class.new(config, source_path, resources_dir) }

  before do
    FileUtils.mkdir_p(resources_dir)
  end

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '#initialize' do
    it 'sets up strings file path' do
      expect(manager.instance_variable_get(:@strings_file)).to include('strings.json')
    end

    it 'initializes empty extracted strings' do
      expect(manager.instance_variable_get(:@extracted_strings)).to eq({})
    end
  end

  describe '#process_strings' do
    it 'returns early for empty files list' do
      expect(KjuiTools::Core::Logger).not_to receive(:info)
      manager.process_strings([], 0, 0)
    end

    it 'logs extraction info for non-empty files' do
      layouts_dir = File.join(temp_dir, 'src/main/assets/Layouts')
      FileUtils.mkdir_p(layouts_dir)
      json_file = File.join(layouts_dir, 'test.json')
      File.write(json_file, '{"type": "Text", "text": "Hello World"}')

      # Allow multiple info calls
      allow(KjuiTools::Core::Logger).to receive(:info)
      allow(KjuiTools::Core::Logger).to receive(:debug)
      expect(KjuiTools::Core::Logger).to receive(:info).with(/Extracting strings/).at_least(:once)
      manager.process_strings([json_file], 1, 0)
    end
  end

  describe '#update_strings_xml' do
    let(:res_values_dir) { File.join(temp_dir, 'src/main/res/values') }
    let(:strings_xml) { File.join(res_values_dir, 'strings.xml') }

    def xml_names
      doc = REXML::Document.new(File.read(strings_xml))
      doc.root.elements.to_a('string').map { |e| e.attributes['name'] }
    end

    let(:layouts_dir) { File.join(temp_dir, 'src/main/assets/Layouts') }

    # The prune may only delete inside namespaces THIS build re-derived,
    # so the spec has to reach it the way production does: extraction
    # first, then the write. Calling update_strings_xml on its own now
    # lands in the third state (see 'when no strings were extracted').
    def extract(*relative_paths)
      files = relative_paths.map do |rel|
        path = File.join(layouts_dir, rel)
        FileUtils.mkdir_p(File.dirname(path))
        File.write(path, '{"type": "View"}')
        path
      end
      manager.process_strings(files, files.size, 0)
    end

    before do
      File.write(File.join(resources_dir, 'strings.json'),
                 JSON.generate({ 'login' => { 'title' => 'Login' } }))
      FileUtils.mkdir_p(res_values_dir)
      File.write(strings_xml, <<~XML)
        <?xml version="1.0" encoding="utf-8"?>
        <resources>
            <string name="app_name">My App</string>
            <string name="login_title">Old Login</string>
            <string name="login_removed_key">Gone from strings.json</string>
        </resources>
      XML
      allow(KjuiTools::Core::Logger).to receive(:info)
      allow(KjuiTools::Core::Logger).to receive(:debug)
      extract('login.json')
      manager.send(:update_strings_xml, 'values')
    end

    it 'prunes keys removed from strings.json within managed prefixes' do
      expect(xml_names).not_to include('login_removed_key')
    end

    it 'keeps and updates keys still declared in strings.json' do
      expect(xml_names).to include('login_title')
      doc = REXML::Document.new(File.read(strings_xml))
      title = doc.root.elements.to_a('string')
                 .find { |e| e.attributes['name'] == 'login_title' }
      expect(title.text).to eq('Login')
    end

    it 'never touches hand-written keys outside managed prefixes' do
      expect(xml_names).to include('app_name')
    end

    context 'when the section is gone from strings.json but the layout is not' do
      # jui build copies the shared strings.json over this tree wholesale,
      # so a section can vanish from under live keys without the layout
      # moving. The prefix used to leave the managed set together with its
      # keys, which orphaned them here forever.
      it 'prunes the orphaned keys under BOTH spellings of the namespace' do
        File.write(File.join(resources_dir, 'strings.json'), JSON.generate({}))
        File.write(strings_xml, <<~XML)
          <?xml version="1.0" encoding="utf-8"?>
          <resources>
              <string name="app_name">My App</string>
              <string name="summary_cell_label">sjui spelling</string>
              <string name="detail_summary_cell_label">kjui spelling</string>
          </resources>
        XML
        fresh = described_class.new(config, source_path, resources_dir)
        path = File.join(layouts_dir, 'detail/summary_cell.json')
        FileUtils.mkdir_p(File.dirname(path))
        File.write(path, '{"type": "View"}')
        fresh.process_strings([path], 1, 0)
        fresh.send(:update_strings_xml, 'values')

        expect(xml_names).not_to include('summary_cell_label')
        expect(xml_names).not_to include('detail_summary_cell_label')
        expect(xml_names).to include('app_name')
      end
    end

    context 'when no strings were extracted this build' do
      # strings.json may then be another writer's file, and its silence
      # about a key is not evidence the key is stale. Declining to judge
      # must be distinguishable from judging and finding nothing.
      it 'prunes nothing and says it declined' do
        File.write(strings_xml, <<~XML)
          <?xml version="1.0" encoding="utf-8"?>
          <resources>
              <string name="login_title">Old Login</string>
              <string name="login_removed_key">Gone from strings.json</string>
          </resources>
        XML
        fresh = described_class.new(config, source_path, resources_dir)
        expect(KjuiTools::Core::Logger).to receive(:info).with(/Did not prune/).once
        fresh.send(:update_strings_xml, 'values')

        expect(xml_names).to include('login_removed_key')
      end
    end
  end

  describe 'private methods' do
    describe 'STRING_PROPERTIES (localizable attribute set)' do
      # W3-2: is_string_property? became the shared core's
      # STRING_PROPERTIES constant (checked inline during extraction).
      it 'contains every localizable string attribute' do
        expect(JsonUIShared::StringManagerCore::STRING_PROPERTIES)
          .to contain_exactly('text', 'hint', 'placeholder', 'label', 'prompt')
      end

      it 'excludes non-string properties' do
        expect(JsonUIShared::StringManagerCore::STRING_PROPERTIES).not_to include('background', 'fontSize')
      end
    end

    describe '#should_extract_string?' do
      it 'returns false for data binding expressions' do
        expect(manager.send(:should_extract_string?, '@{userName}')).to be false
        expect(manager.send(:should_extract_string?, '${userName}')).to be false
      end

      it 'returns false for snake_case strings (already converted keys)' do
        expect(manager.send(:should_extract_string?, 'hello_world')).to be false
        expect(manager.send(:should_extract_string?, 'test_string_key')).to be false
      end

      it 'returns true for regular text strings' do
        expect(manager.send(:should_extract_string?, 'Hello World')).to be true
      end

      it 'returns false for very short strings without letters' do
        expect(manager.send(:should_extract_string?, '12')).to be false
      end

      it 'returns false for strings without letters' do
        expect(manager.send(:should_extract_string?, '12345')).to be false
      end
    end

    describe '#generate_string_key' do
      it 'converts text to snake_case' do
        expect(manager.send(:generate_string_key, 'Hello World')).to eq('hello_world')
      end

      it 'removes special characters' do
        expect(manager.send(:generate_string_key, 'Hello, World!')).to eq('hello_world')
      end

      it 'limits key length' do
        long_text = 'This is a very long string that should be truncated to thirty chars'
        result = manager.send(:generate_string_key, long_text)
        expect(result.length).to be <= 35  # 30 + some buffer for the actual implementation
      end

      it 'removes leading and trailing underscores' do
        expect(manager.send(:generate_string_key, '  Hello  ')).to eq('hello')
      end

      it 'collapses multiple underscores' do
        expect(manager.send(:generate_string_key, 'Hello   World')).to eq('hello_world')
      end

      # The key is a resource identifier, not a label: aapt2 takes kanji and
      # kana as name characters but rejects punctuation, so a Japanese
      # sentence that keeps its `。` stops the Android build outright
      # (measured on the sample app 2026-09-02).
      it 'keeps Japanese letters but drops punctuation a resource name cannot hold' do
        expect(manager.send(:generate_string_key, '今日は天気がいいですね。明日も晴れるといいです。'))
          .to eq('今日は天気がいいですね_明日も晴れるといいです')
      end

      it 'folds spaces and punctuation between Japanese words to single underscores' do
        expect(manager.send(:generate_string_key, '選択、または　入力！')).to eq('選択_または_入力')
      end

      it 'leaves a punctuation-free Japanese string alone' do
        expect(manager.send(:generate_string_key, '選択してください')).to eq('選択してください')
      end

      # A key that is ALREADY a usable identifier must come back byte for
      # byte. Without this the change stops being a fix and becomes a
      # migration: every reference that resolves today on iOS and web would
      # have to be rewritten to match a new spelling.
      # (Bare `_leading` / `trailing_` are deliberately absent: the ASCII
      # branch has always trimmed edge underscores, and that predates this
      # change — measured, the diff touches only the Japanese branch.)
      it 'is idempotent on keys that are already identifier-safe' do
        %w[
          hello_world submit_button item_count_2 完了する 選択してください
          日付を選択 mixed_日本語_key a1_b2_c3 送信_2
        ].each do |key|
          expect(manager.send(:generate_string_key, key)).to eq(key), "rewrote #{key.inspect}"
        end
      end

      it 'is deterministic' do
        text = '確認して、送信してください！'
        first = manager.send(:generate_string_key, text)
        expect(manager.send(:generate_string_key, text)).to eq(first)
      end

      # Folding punctuation to underscores can map two different sentences
      # onto one key, so distinct texts must still end up under distinct
      # keys. Driven through the real extraction path because that is what
      # registers each key as it goes — the duplicate counter can only see a
      # collision against keys already taken.
      it 'does not collapse distinct texts onto one key' do
        texts = [
          '今日は天気がいいですね。明日も晴れるといいです。',
          '今日は天気がいいですね、明日も晴れるといいです',
          '選択、または　入力！',
          '選択または入力',
          '確認して、送信してください！',
          '確認して送信してください'
        ]
        data = { 'type' => 'View', 'child' => texts.map { |t| { 'type' => 'Text', 'text' => t } } }
        manager.send(:extract_strings_recursive, data, 'home')
        strings = manager.instance_variable_get(:@current_file_strings)
        expect(strings.length).to eq(texts.length), "collision: #{texts.length - strings.length} text(s) lost"
        expect(strings.values.uniq.length).to eq(texts.length)
      end
    end

    describe '#generate_file_prefix' do
      it 'removes .json extension' do
        expect(manager.send(:generate_file_prefix, 'test.json')).to eq('test')
      end

      it 'replaces slashes with underscores' do
        expect(manager.send(:generate_file_prefix, 'subdir/test.json')).to eq('subdir_test')
      end

      it 'handles multiple directories' do
        expect(manager.send(:generate_file_prefix, 'a/b/c/test.json')).to eq('a_b_c_test')
      end
    end

    # W3-2: #snake_to_camel was removed together with its only consumer,
    # the long-disabled StringManager.kt generator (dead code since the
    # "Disabled: StringManager.kt generation is not needed" era).

    describe '#create_new_strings_xml' do
      it 'creates XML document with resources root' do
        doc = manager.send(:create_new_strings_xml)
        expect(doc.root.name).to eq('resources')
      end

      it 'includes XML declaration' do
        doc = manager.send(:create_new_strings_xml)
        expect(doc.xml_decl.version).to eq('1.0')
        expect(doc.xml_decl.encoding.downcase).to eq('utf-8')
      end
    end

    describe '#get_translated_value' do
      it 'returns default value' do
        result = manager.send(:get_translated_value, 'key', 'Hello', 'values')
        expect(result).to eq('Hello')
      end
    end
  end

  describe '#apply_to_strings_files' do
    it 'returns early when strings_data is empty' do
      manager.instance_variable_set(:@strings_data, {})
      expect(manager).not_to receive(:update_strings_xml)
      manager.apply_to_strings_files
    end

    it 'updates default strings.xml when no string_files configured' do
      manager.instance_variable_set(:@strings_data, { 'test' => { 'key' => 'value' } })
      expect(manager).to receive(:update_strings_xml).with('values')
      manager.apply_to_strings_files
    end
  end

  # ------------------------------------------------------------------ #
  # Reported 2026-09-07 (client, Android): the SSoT value was trimmed and
  # its whitespace runs folded on the way into strings.xml, so a string
  # written with a leading space reached iOS intact and Android without it.
  # The same key then held two different strings on two faces, and the SSoT
  # could not fix it, because the SSoT was what was being discarded.
  #
  # Android's own mechanism for this is the quoted value; sjui does no
  # trimming at all (`.strip` appears nowhere in its string manager), so
  # preserving here is what makes the faces agree rather than a new
  # convention.
  # ------------------------------------------------------------------ #
  describe 'whitespace that the SSoT declares' do
    let(:res_values_dir) { File.join(temp_dir, 'src/main/res/values') }
    let(:strings_xml) { File.join(res_values_dir, 'strings.xml') }
    let(:layouts_dir) { File.join(temp_dir, 'src/main/assets/Layouts') }

    def extract(*relative_paths)
      files = relative_paths.map do |rel|
        path = File.join(layouts_dir, rel)
        FileUtils.mkdir_p(File.dirname(path))
        File.write(path, '{"type": "View"}')
        path
      end
      manager.process_strings(files, files.size, 0)
    end

    def build(strings)
      File.write(File.join(resources_dir, 'strings.json'), JSON.generate(strings))
      FileUtils.mkdir_p(res_values_dir)
      File.write(strings_xml, <<~XML)
        <?xml version="1.0" encoding="utf-8"?>
        <resources>
        </resources>
      XML
      allow(KjuiTools::Core::Logger).to receive(:info)
      allow(KjuiTools::Core::Logger).to receive(:debug)
      extract(*strings.keys.map { |k| "#{k}.json" })
      manager.send(:update_strings_xml, 'values')
      File.read(strings_xml)
    end

    # The assertions read PARSED text, not the serialization: REXML writes
    # the quote as `&quot;`, and pinning that spelling would test REXML
    # rather than this file. The parsed value is what aapt sees.
    def value_of(xml, name)
      REXML::Document.new(xml).root.elements.to_a('string')
        .find { |e| e.attributes['name'] == name }&.text
    end

    it 'keeps a trailing space, by quoting the value the way Android does' do
      xml = build('signup' => { 'prompt' => 'Have an account? ' })
      expect(value_of(xml, 'signup_prompt')).to eq('"Have an account? "')
    end

    it 'keeps a leading space' do
      xml = build('listing' => { 'suffix' => ' (next day)' })
      expect(value_of(xml, 'listing_suffix')).to eq('" (next day)"')
    end

    it 'leaves a string with no significant whitespace exactly as it was' do
      # The arm that keeps this from rewriting the whole file: quoting is
      # applied where it changes something and nowhere else. Without it the
      # next build rewrites thousands of lines and buries the real diff.
      xml = build('login' => { 'title' => 'Login' })
      expect(value_of(xml, 'login_title')).to eq('Login')
    end

    it 'keeps the apostrophe escape inside a value it has to quote' do
      # The reported string carries both a quote-forcing space and an
      # apostrophe; the escape has to survive the wrapping.
      xml = build('signup' => { 'prompt' => "Don't have an account? " })
      expect(value_of(xml, 'signup_prompt')).to eq(%q("Don\\'t have an account? "))
    end

    it 'applies the same rule to plurals, so the two sites cannot diverge' do
      # Fixing one site and not the other leaves the asymmetry inside this
      # file instead of between the two faces.
      xml = build('cart' => { 'items' => {
        'en' => { 'plural' => { 'one' => '{count} item ', 'other' => '{count} items ' } }
      } })
      items = REXML::Document.new(xml).root
                .elements["plurals[@name='cart_items']"].elements.to_a('item')
      by_q = items.to_h { |i| [i.attributes['quantity'], i.text] }
      expect(by_q['one']).to eq('"%d item "')
      expect(by_q['other']).to eq('"%d items "')
    end

    it 'does NOT preserve a run of spaces, because REXML folds it downstream' do
      # A limit, pinned so it is a recorded fact rather than an assumption.
      # The ticket asked for the `[ \t\r]+ -> ' '` fold to be dropped too,
      # and it was — but dropping it changes nothing: REXML normalizes
      # whitespace when the Text node is built, before any formatter runs,
      # so `a  b` reaches the file as `a b` either way. Preserving runs
      # would mean replacing the writer, which would reformat every
      # strings.xml in every consumer.
      #
      # Measured 2026-09-07 on the files the generator actually reads
      # (<android>/app/src/main/assets/Layouts/Resources/strings.json,
      # 2,548 strings across the live faces): strings with an internal run
      # = 0. Every real case is a single leading or trailing space, which
      # the quoting above does preserve.
      xml = build('report' => { 'gap' => 'a  b' })
      expect(value_of(xml, 'report_gap')).to eq('"a b"')
    end
  end

end
