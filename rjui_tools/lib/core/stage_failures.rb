# frozen_string_literal: true

module JsonUI
  # Stages that failed while the build carried on.
  #
  # A build has stages that can fail without the build being wrong to
  # continue: an unreadable colors.json means this run cannot say anything
  # about colours, not that the layouts are broken. Stopping there helps
  # nobody, so those stages log and carry on — and the log then scrolls
  # past, leaving a successful-looking tail that says nothing about it.
  #
  # Measured: a run that could not parse colors.json printed a warning at
  # line 13 of 46 and finished with `Build completed!` and exit 0. A reader
  # who scrolls to the bottom, which is where a reader looks, saw only the
  # success.
  #
  # NOT AN EXIT CODE. The build is not wrong to finish, and turning these
  # into failures would break the window every consuming project builds in.
  # What was missing is that the end of the run says what it could not do.
  #
  # NOTHING IS PRINTED WHEN NOTHING FAILED, so a healthy run's output is
  # byte-identical to before and no downstream baseline moves.
  module StageFailures
    class << self
      def record(stage, message)
        entries << { stage: stage.to_s, message: message.to_s }
      end

      # For a failure met on every visit — a config file every load reads,
      # a style every layout using it loads — which is one failure however
      # often it is met.
      def record_once(stage, message)
        return if entries.any? { |e| e[:stage] == stage.to_s && e[:message] == message.to_s }

        record(stage, message)
      end

      def entries
        @entries ||= []
      end

      def any?
        entries.any?
      end

      def clear!
        @entries = []
        @written = 0
        @blocked_layouts = {}
      end

      # A layout whose bindings carry an ERROR is not written: its generated
      # files (view, Data, ViewModel, hook — every writer asks
      # `layout_blocked?`) stay as the last good build left them, and the
      # stage line says so. Until jsonui-cli 1.9.8 the build wrote them and
      # then exited 1 — a failed build that had replaced good files with
      # broken ones (ticket failed-build-writes-the-generated-files). Keyed by
      # the absolute path, so a relative and an absolute spelling are one.
      def block_layout(path, reason)
        key = File.expand_path(path.to_s)
        return if blocked_layouts.key?(key)

        blocked_layouts[key] = reason.to_s
        record('layout', "#{path} was not written: #{reason} — its generated files are the last build's")
      end

      def layout_blocked?(path)
        blocked_layouts.key?(File.expand_path(path.to_s))
      end

      def blocked_layouts
        @blocked_layouts ||= {}
      end

      # The closing line of a build: the success line only when nothing
      # failed. One sentence for every face — the UIKit and Compose builds
      # said they completed directly under the list of what had not until
      # 1.9.0 (ticket uikit-build-reports-success-after-a-binding-error).
      # The exit code is left alone, as above: `jui build` turns the ledger
      # into the non-zero exit.
      def conclude(logger, success_line)
        if any?
          logger.error("Build finished with #{entries.size} stage(s) incomplete — see above")
        else
          logger.success(success_line)
        end
      end

      # Called at the end of a build. `logger` is the platform's own.
      #
      # Also appends to the file named by JUI_STAGE_FAILURES when the
      # orchestrating `jui build` set it. Each platform tool is a separate
      # process, so naming the failure at this terminus still leaves it
      # above the orchestrator's own closing block — which is the bottom a
      # reader actually looks at. The file is how it gets there; the
      # variable is set by the caller, so nothing has to guess a path.
      def report!(logger)
        write_ledger
        return if entries.empty?

        logger.error(
          "#{entries.size} stage(s) did not complete; the build carried on " \
          'without them:'
        )
        entries.each do |e|
          logger.error("  - #{e[:stage]}: #{e[:message]}")
        end
      end

      private

      def write_ledger
        path = ENV['JUI_STAGE_FAILURES']
        return if path.nil? || path.empty? || entries.empty?

        require 'json'
        existing = begin
          JSON.parse(File.read(path))
        rescue StandardError
          []
        end
        existing = [] unless existing.is_a?(Array)
        # Only what this process has not written yet: `sjui build --mode all`
        # reports at the end of the UIKit stage and again at the end of the
        # SwiftUI one, and until 1.9.0 the second report wrote the first
        # one's entries again — one unparseable colors.json was two stages
        # in `jui build`'s count.
        written = @written || 0
        written = 0 if written > entries.size
        added = entries.drop(written).map do |e|
          { 'stage' => e[:stage], 'message' => e[:message] }
        end
        return if added.empty?

        merged = existing + added
        File.write(path, JSON.generate(merged))
        @written = entries.size
      rescue StandardError
        nil
      end
    end
  end
end
