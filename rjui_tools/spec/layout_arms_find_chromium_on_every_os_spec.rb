# frozen_string_literal: true

require 'fileutils'
require 'tmpdir'
require_relative 'spec_helper'
require_relative 'support/headless_chromium'

# The layout arms' browser lookup (spec/support/headless_chromium.rb).
#
# Until jsonui-cli 1.9.9 four specs looked only in macOS's Playwright cache,
# so on CI's Linux leg the 13 arms were pending on every run (ticket
# rjui-chromium-arms-never-run-in-ci). The caches here are built in a temp
# dir in each OS's shape.
RSpec.describe HeadlessChromium do
  def shell(root, revision, platform)
    file = File.join(root, "chromium_headless_shell-#{revision}", platform, 'chrome-headless-shell')
    FileUtils.mkdir_p(File.dirname(file))
    File.write(file, '')
    File.chmod(0o755, file)
    file
  end

  around do |example|
    Dir.mktmpdir('headless_chromium') do |dir|
      @dir = dir
      example.run
    end
  end

  it "finds Linux's cache shape (~/.cache/ms-playwright/…/chrome-headless-shell-linux64)" do
    linux = File.join(@dir, 'home', '.cache', 'ms-playwright')
    found = shell(linux, 1234, 'chrome-headless-shell-linux64')
    expect(described_class.path([File.join(@dir, 'home', 'Library', 'Caches', 'ms-playwright'), linux])).to eq(found)
  end

  it "finds macOS's cache shape" do
    mac = File.join(@dir, 'Library', 'Caches', 'ms-playwright')
    found = shell(mac, 1234, 'chrome-headless-shell-mac-arm64')
    expect(described_class.path([mac])).to eq(found)
  end

  it 'takes the newest revision by number, not by text (999 is older than 1200)' do
    shell(@dir, 999, 'chrome-headless-shell-linux64')
    newest = shell(@dir, 1200, 'chrome-headless-shell-linux64')
    expect(described_class.path([@dir])).to eq(newest)
  end

  it 'reads PLAYWRIGHT_BROWSERS_PATH first, as Playwright does' do
    old = ENV.fetch('PLAYWRIGHT_BROWSERS_PATH', nil)
    ENV['PLAYWRIGHT_BROWSERS_PATH'] = @dir
    expect(described_class.caches.first).to eq(@dir)
  ensure
    old ? ENV['PLAYWRIGHT_BROWSERS_PATH'] = old : ENV.delete('PLAYWRIGHT_BROWSERS_PATH')
  end

  it 'is nil where no cache holds one' do
    expect(described_class.path([File.join(@dir, 'none')])).to be_nil
  end

  it 'fails, not skips, when the run says it installed the browser' do
    old = ENV.fetch(described_class::REQUIRE_ENV, nil)
    ENV[described_class::REQUIRE_ENV] = '1'
    allow(described_class).to receive(:path).and_return(nil)
    expect { described_class.ensure!(self) }.to raise_error(/RJUI_SPEC_REQUIRE_CHROMIUM=1/)
  ensure
    old ? ENV[described_class::REQUIRE_ENV] = old : ENV.delete(described_class::REQUIRE_ENV)
  end
end
