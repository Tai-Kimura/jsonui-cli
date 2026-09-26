# frozen_string_literal: true

require 'json'
require 'open3'
require 'rbconfig'
require 'tmpdir'
require_relative '../../spec_helper'
require 'core/config_manager'

# A project that changed `typescript`: what earlier builds wrote in the other
# language (`Home.tsx` beside the `Home.jsx` this build writes — both answer
# `import Home from '…/Home'`) is replaced. The layout-orphan sweep does not
# see these files, since their layouts are all there; measured on deaead11 +
# the JavaScript fixes (3f116e4a): a project built as TypeScript and rebuilt as
# JavaScript kept all 29 of its TypeScript files, a no-key project from the
# old tools all 17. The build deletes a file in the other language whose
# same-named file it wrote in this one when the file is the generator's by the
# test its own refresh uses (GeneratedOrphans.sweep_replaced); it names the
# rest — a copy the user owns (Configuration is theirs once written), and a
# ViewModel the user wrote in the other language, whose base and hook follow
# it. Nothing the user wrote is deleted.
#
# EmbedContainer (round 8): `rjui init` writes it and no build does, so
# nothing replaced it and it was not named either. Now init's copy unchanged
# is replaced — this language's copy written, the old deleted — and one that
# is not (edited below the mark, or unmarked) is named and kept, with no copy
# written beside it.
RSpec.describe 'rjui build: the copies in the other language' do
  def rjui(dir, *args)
    out, status = Open3.capture2e(RbConfig.ruby, File.expand_path('../../../bin/rjui', __dir__), *args, chdir: dir)
    raise "rjui #{args.join(' ')}: #{out}" unless status.success?

    out.gsub(/\e\[[0-9;]*m/, '')
  end

  def configure(dir, typescript)
    path = File.join(dir, 'rjui.config.json')
    File.write(path, JSON.pretty_generate(JSON.parse(File.read(path)).merge('typescript' => typescript)))
  end

  def files(dir, *exts)
    Dir.glob(File.join(dir, '**', '*')).select { |f| File.file?(f) && exts.include?(File.extname(f)) }
       .map { |f| f.sub("#{dir}/", '') }.sort
  end

  # A project written in `from` (its config first, so `rjui init` writes in
  # that language too), then built in the other language.
  # `beside`: this language's EmbedContainer is there before the build (a
  # later `rjui init` wrote it).
  def switched(from:, embed: nil, beside: false)
    Dir.mktmpdir('rjui_switch') do |dir|
      File.write(File.join(dir, 'rjui.config.json'),
                 JSON.pretty_generate(RjuiTools::Core::ConfigManager::DEFAULT_CONFIG.merge('typescript' => from == :typescript)))
      rjui(dir, 'init')
      rjui(dir, 'g', 'view', 'home_screen')
      rjui(dir, 'g', 'component', 'chip_card')
      rjui(dir, 'build')
      configuration = Dir.glob(File.join(dir, 'src/lib/jsonui/Configuration.*')).first
      File.write(configuration, "#{File.read(configuration)}// the host's own font provider\n")
      embed_path = Dir.glob(File.join(dir, 'src/components/extensions/EmbedContainer.*')).first
      File.write(embed_path, embed.call(File.read(embed_path))) if embed
      if beside
        name = from == :typescript ? 'js/EmbedContainer.jsx' : 'EmbedContainer.tsx'
        File.write(File.join(dir, 'src/components/extensions', File.basename(name)),
                   File.read(File.expand_path("../../../lib/react/templates/#{name}", __dir__)))
      end
      edited = File.join(dir, 'src/generated/data', from == :typescript ? 'HomeScreenData.ts' : 'HomeScreenData.js')
      before = files(dir, '.ts', '.tsx', '.js', '.jsx')
      configure(dir, from != :typescript)
      log = rjui(dir, 'build')
      yield dir, log, before, File.exist?(edited)
    end
  end

  it 'TypeScript to JavaScript: the generated TypeScript copies are replaced, the user files kept and named' do
    switched(from: :typescript) do |dir, log, before, _|
      left = files(dir, '.ts', '.tsx')
      # The user's: the page and the ViewModels `g` wrote, the Configuration they
      # edited — and the base and hook each ViewModel's language asks for.
      expect(left).to eq(%w[
        src/app/home-screen/page.tsx
        src/generated/hooks/useChipCardViewModel.ts
        src/generated/hooks/useHomeScreenViewModel.ts
        src/generated/viewmodels/ChipCardViewModelBase.ts
        src/generated/viewmodels/HomeScreenViewModelBase.ts
        src/lib/jsonui/Configuration.ts
        src/viewmodels/ChipCardViewModel.ts
        src/viewmodels/HomeScreenViewModel.ts
      ])
      expect(before.grep(/\.tsx?\z/).size).to be > left.size + 15 # the components, data, helpers, built-ins were there
      %w[src/generated/components/HomeScreen.tsx src/generated/data/HomeScreenData.ts src/generated/ColorManager.ts
         src/generated/hooks/useColorMode.ts src/components/extensions/NetworkImage.tsx
         src/components/extensions/EmbedContainer.tsx].each do |gone|
        expect(before).to include(gone)
        expect(log).to include("  - #{gone} (now #{File.basename(gone).sub(/\.ts\z/, '.js').sub(/\.tsx\z/, '.jsx')})")
      end
      expect(log).to include('src/lib/jsonui/Configuration.ts: Configuration.js replaces it, but it is not marked')
      expect(log).to include('2 ViewModel(s) of this JavaScript project are in the other language')
      expect(File.read(File.join(dir, 'src/lib/jsonui/Configuration.ts'))).to include("the host's own font provider")
      # This language's EmbedContainer is init's, as `rjui init` would write it.
      expect(File.read(File.join(dir, 'src/components/extensions/EmbedContainer.jsx')))
        .to eq(File.read(File.expand_path('../../../lib/react/templates/js/EmbedContainer.jsx', __dir__)))
    end
  end

  {
    'edited below its mark' => [->(text) { "#{text}// the host's own routing\n" }, "carries `rjui init`'s mark but is not the copy init writes"],
    'without the mark' => [->(text) { text.sub('Generated by rjui_tools `rjui init`', 'Ours') }, "does not carry `rjui init`'s mark"]
  }.each do |shape, (edit, why)|
    it "an EmbedContainer #{shape}, with this language's copy already beside it, is kept and named once" do
      switched(from: :typescript, embed: edit, beside: true) do |dir, log, _, _|
        kept = File.join(dir, 'src/components/extensions/EmbedContainer.tsx')
        expect(File.read(kept)).to eq(edit.call(File.read(File.expand_path('../../../lib/react/templates/EmbedContainer.tsx', __dir__))))
        expect(log).to include("src/components/extensions/EmbedContainer.tsx is in the other language and was kept: it #{why}")
        expect(log).to include('EmbedContainer.jsx is beside it and answers the same import')
        expect(log.scan('EmbedContainer.tsx').size).to eq(1), log
      end
    end

    it "an EmbedContainer #{shape} is kept and named, and no copy is written beside it" do
      switched(from: :typescript, embed: edit) do |dir, log, _, _|
        kept = File.join(dir, 'src/components/extensions/EmbedContainer.tsx')
        expect(File.read(kept)).to eq(edit.call(File.read(File.expand_path('../../../lib/react/templates/EmbedContainer.tsx', __dir__))))
        expect(File.exist?(File.join(dir, 'src/components/extensions/EmbedContainer.jsx'))).to be(false)
        expect(log).to include("src/components/extensions/EmbedContainer.tsx is in the other language and was kept: it #{why}")
      end
    end
  end

  it 'JavaScript to TypeScript: the same, the other way' do
    switched(from: :javascript) do |dir, log, before, edited_left|
      left = files(dir, '.js', '.jsx')
      expect(left).to eq(%w[
        src/app/home-screen/page.jsx
        src/generated/hooks/useChipCardViewModel.js
        src/generated/hooks/useHomeScreenViewModel.js
        src/generated/viewmodels/ChipCardViewModelBase.js
        src/generated/viewmodels/HomeScreenViewModelBase.js
        src/lib/jsonui/Configuration.js
        src/viewmodels/ChipCardViewModel.js
        src/viewmodels/HomeScreenViewModel.js
      ])
      expect(before).to include('src/generated/components/HomeScreen.jsx')
      expect(edited_left).to be(false)
      expect(log).to include('  - src/generated/components/HomeScreen.jsx (now HomeScreen.tsx)')
      expect(log).to include('  - src/components/extensions/EmbedContainer.jsx (now EmbedContainer.tsx)')
    end
  end

  it 'control: a build with no language change prunes nothing and names nothing' do
    Dir.mktmpdir('rjui_same') do |dir|
      rjui(dir, 'init')
      configure(dir, false)
      rjui(dir, 'g', 'view', 'home_screen')
      rjui(dir, 'build')
      log = rjui(dir, 'build')
      expect(log).not_to include('output replaces')
      expect(log).not_to include('in the other language')
      expect(Dir.glob(File.join(dir, 'src/components/extensions/EmbedContainer.*')).map { |f| File.basename(f) }).to eq(%w[EmbedContainer.jsx])
    end
  end
end
