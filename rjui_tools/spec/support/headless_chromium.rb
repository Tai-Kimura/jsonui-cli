# frozen_string_literal: true

# The headless Chromium the layout arms draw emitted React in.
#
# WHY ONE PLACE
#
# Four specs (collection scroll-to-cell, flow sections, horizontal lanes, the
# RTL safe-area insets) each looked for the browser themselves, and all four
# looked only in macOS's Playwright cache (~/Library/Caches/ms-playwright).
# CI's rjui leg runs on Linux, where Playwright keeps it in ~/.cache — so the
# 13 arms were pending on every CI run since jsonui-cli 1.9.0, and installing
# the browser there would not have changed it (ticket
# rjui-chromium-arms-never-run-in-ci).
#
# WHERE IT COMES FROM
#
# `spec/support/package.json` pins playwright; `npx --prefix
# rjui_tools/spec/support playwright install --only-shell chromium` puts the
# headless shell in the cache. PLAYWRIGHT_BROWSERS_PATH is read first, as
# Playwright itself does.
#
# A MISSING BROWSER IS A SKIP — EXCEPT WHERE IT WAS INSTALLED
#
# On a machine without it the arms skip and say why. CI's rjui leg installs
# it and sets RJUI_SPEC_REQUIRE_CHROMIUM=1, and there a missing browser fails
# the example: from 1.9.0 to 1.9.8 the arms were pending in CI and the run
# was green, because a skip looked like nothing.
module HeadlessChromium
  module_function

  REQUIRE_ENV = 'RJUI_SPEC_REQUIRE_CHROMIUM'

  # How every arm starts it. `--no-sandbox` because the CI runner (Ubuntu
  # 24.04) restricts unprivileged user namespaces with AppArmor, and the
  # browser then dies before drawing: "No usable sandbox!" — measured on the
  # first CI run that had a browser (37123828134, all 13 arms). Playwright
  # itself launches Chromium without the sandbox by default; the page is a
  # local file the spec wrote.
  FLAGS = %w[--headless --disable-gpu --no-sandbox].freeze

  def caches
    [ENV['PLAYWRIGHT_BROWSERS_PATH'],
     File.join(Dir.home, 'Library', 'Caches', 'ms-playwright'),
     File.join(Dir.home, '.cache', 'ms-playwright')].compact.reject(&:empty?)
  end

  # The newest headless shell in the first cache that holds one. "Newest" by
  # the revision number, not the string: chromium_headless_shell-999 sorts
  # after -1200 as text.
  def path(roots = caches)
    roots.each do |root|
      found = Dir.glob(File.join(root, 'chromium_headless_shell-*', '*', 'chrome-headless-shell'))
                 .select { |f| File.executable?(f) }
      next if found.empty?

      return found.max_by { |f| f[%r{chromium_headless_shell-(\d+)/}, 1].to_i }
    end
    nil
  end

  def required?
    ENV[REQUIRE_ENV] == '1'
  end

  # Called from an example (or a helper an example calls): skips when there
  # is no browser, or fails when this run declared it installed.
  def ensure!(example)
    return path if path

    reason = "no headless Chromium in the Playwright cache (looked in #{caches.join(', ')})"
    raise "#{reason} — #{REQUIRE_ENV}=1 says this run installed it" if required?

    example.skip reason
  end
end
