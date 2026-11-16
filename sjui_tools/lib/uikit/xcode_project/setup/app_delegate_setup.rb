#!/usr/bin/env ruby

require "fileutils"

module SjuiTools
  module UIKit
    module XcodeProject
      module Setup
        class AppDelegateSetup
          def initialize(project_file_path)
            @project_file_path = project_file_path
          end

          def add_hotloader_functionality
            puts "Adding HotLoader functionality to AppDelegate..."
            
            # AppDelegate.swiftファイルを探す
            # @project_file_pathが.xcodeprojかproject.pbxprojかを確認
            if @project_file_path.end_with?('.pbxproj')
              # project.pbxprojの場合は2階層上がプロジェクトディレクトリ
              project_dir = File.dirname(File.dirname(File.dirname(@project_file_path)))
            else
              # .xcodeprojディレクトリの場合は親ディレクトリがプロジェクトディレクトリ
              project_dir = File.dirname(@project_file_path)
            end
            
            app_delegate_path = find_app_delegate_file(project_dir)
            
            if app_delegate_path.nil?
              puts "Warning: UIApplicationDelegate に適合する型が見つかりません " \
                   "(`@UIApplicationDelegateAdaptor` が名指す型 / `: UIApplicationDelegate` / AppDelegate.swift のいずれも不在)。" \
                   "HotLoader は有効になりません。"
              return
            end

            puts "Updating app delegate: #{app_delegate_path}"
            
            # AppDelegate.swiftの内容を読み込む
            content = File.read(app_delegate_path)
            
            # この版の生成節（マーカー）が既に在るかだけを見る。
            # ⚠️ 2026-09-14 まではここが `content.include?("HotLoader.instance")` だった。
            # 旧生成物は必ずその文字列を含むので、**既に setup 済のプロジェクトには以後どんな変更も届かず**、
            # しかも "already exists" と成功の顔で印字されていた（scene 移行が構造的に配れない）。
            if current_region?(content) && scene_up_to_date?(project_dir)
              puts "HotLoader region is already up to date in AppDelegate"
              return
            end
            
            # AppDelegate.swiftにHotLoader機能を追加
            updated_content = add_hotloader_content(content)
            
            # ファイルに書き戻す
            File.write(app_delegate_path, updated_content)
            puts "HotLoader functionality added to AppDelegate successfully"

            # v2: on/off は scene 側。届かないときは**黙って AppDelegate に戻さない**
            # （戻すと、アプリが scene 化した後の再 setup で旧型に巻き戻り、
            #  消費側は壊れたことに気づけない）。
            scene_path = update_scene_delegate(project_dir)
            # 生成した先（AppDelegate 相当と SceneDelegate）以外に配線が在れば名指しする
            wiring = report_existing_wiring(project_dir, [app_delegate_path, scene_path].compact)
            annotate_generated_region(app_delegate_path, wiring) unless wiring.empty?
          end

          private

          # delegate は**型の綴り**で探す。ファイル名で探してはいけない。
          #
          # ⚠️ 実測 (2026-09-14): `jui.config.json` が ios を宣言する木には
          #   `AppDelegate.swift` が **0 本**。SwiftUI ライフサイクル
          #   （`@main struct XxxApp: App` ＋ `@UIApplicationDelegateAdaptor(AppDelegate.self)`）
          #   では delegate クラスが App 本体のファイルの中に在る。
          #   ファイル名 glob はそこで nil を返し、警告 1 行 ＋ **exit 0** で終わっていた
          #   ＝ setup の HotLoader 経路がその木では**一度も走っていない**。
          #   「注入先が AppDelegate 固定」より手前の、**探索の綴り**が母集団を決めていた。
          #
          # 優先順位: ① `@UIApplicationDelegateAdaptor(X.self)` が名指す型 X の定義
          #           ② `UIApplicationDelegate` に適合する型の定義
          #           ③ 従来の `AppDelegate.swift`（①②が無い木のための最後の砦）
          APP_DELEGATE_ADAPTOR = /@UIApplicationDelegateAdaptor(?:\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\.self\s*\))?/
          def find_app_delegate_file(project_dir)
            swift_files = Dir.glob("#{project_dir}/**/*.swift").reject { |path| ignored_path?(path) }
                             .sort_by { |path| [path.split("/").length, path] }

            named = adaptor_named_type(swift_files)
            if named
              hit = swift_files.find { |path| File.read(path) =~ /(?:class|struct)\s+#{Regexp.escape(named)}\b/ }
              return hit if hit
            end

            hit = swift_files.find { |path| File.read(path) =~ /(?:class|struct)\s+\w+[^{\n]*:\s*[^{\n]*\bUIApplicationDelegate\b/ }
            return hit if hit

            swift_files.find { |path| File.basename(path) == "AppDelegate.swift" }
          rescue StandardError
            nil
          end

          # 区間の外に在る既存の HotLoader 配線を**名指しする**（消さない）。
          #
          # ⚠️ 到達していなかった木は、その間に自分で配線している。実測: App ファイルの
          #   `init()` の `#if DEBUG` に 5 行、うち 1 行が `isHotLoadEnabled = true`。
          #   探索を直して到達させると、SceneDelegate に区間が入る一方でこの行は残り、
          #   **有効化が 2 系統**になる。到達させる修正は、到達先で二重になるを連れてくる。
          #
          # 処置は検出と名乗りまで。**剥がさない・動かさない・書き換えない**——区間の外は
          # 消費側の territory で、置き換えないなら取り上げない。
          def existing_wiring(project_dir, generated_paths)
            found = []
            Dir.glob("#{project_dir}/**/*.swift").reject { |path| ignored_path?(path) }.sort.each do |path|
              lines = outside_generated_regions(File.readlines(path))
              lines.each do |lineno, line|
                next unless line =~ /HotLoader\s*\.\s*instance/

                found << [path, lineno, line.strip]
              end
            end
            found.reject { |path, _lineno, _line| generated_paths.include?(path) }
          rescue StandardError
            []
          end

          # 行番号つきで、生成区間の**外**の行だけを返す
          def outside_generated_regions(lines)
            inside = false
            out = []
            lines.each_with_index do |line, i|
              if line.include?(MARKER_PREFIX)
                inside = true
                next
              end
              if line.include?(MARKER_END)
                inside = false
                next
              end
              out << [i + 1, line] unless inside
            end
            out
          end

          # 同じ事実の読み手が 3 つあり、寿命が違う:
          #   stdout の Note   撃った人向け    その実行だけ
          #   区間内コメント     次に開く人向け  次の setup 実行まで
          #   票 / 報告書       設計を追う人    恒久（散文なので腕では pin できない）
          # ⇒ **機械が出す 2 つは 1 か所から組む**。別々に書くと、次に文言を直す人が
          #   片方だけ直し、読み手ごとに違う事実が届く。
          WIRING_HEADLINE = "HotLoader の配線が区間の外にもあります"

          # 識別フィールド: ファイル名 ＋ **綴り** ＋ 行番号（綴りの補助）
          def wiring_fields(wiring)
            wiring.map { |path, lineno, line| "#{File.basename(path)} (#{line}) 付近 L#{lineno}" }.join(" / ")
          end

          def wiring_provenance
            "#{setup_version} が #{observation_date} に観測"
          end

          def report_existing_wiring(project_dir, generated_paths)
            wiring = existing_wiring(project_dir, generated_paths)
            return [] if wiring.empty?

            puts "Note: #{WIRING_HEADLINE} —— #{wiring_fields(wiring)} [#{wiring_provenance}]。" \
                 "生成区間の外なので sjui は管理しません——このままだと有効化が 2 系統になります。" \
                 "残すかどうかは消費側の判断です（sjui は消しません）。"
            wiring
          end

          def adaptor_named_type(swift_files)
            swift_files.each do |path|
              m = File.read(path).match(APP_DELEGATE_ADAPTOR)
              return m[1] if m && m[1]
            end
            nil
          end

          # 生成した節はマーカーで囲む。削除はこの区間だけを対象にし、
          # 区間の外側（消費側が書いた行）には一切触れない。
          # 区間は版を名乗る。ガードは「マーカーが在るか」でなく
          # 「**この版の**マーカーが在るか」を見る——版を上げた setup（例: 注入先を
          # SceneDelegate に移す変更）が、既に setup 済のプロジェクトに届くようにするため。
          # 版が古い区間は剥がして貼り直す（区間の外は触らない）。
          # v2 (2026-09-14): ライフサイクルの on/off は SceneDelegate 側へ移した。
          # iOS 27 SDK では scene ライフサイクル必須で、`application*` は呼ばれない。
          REGION_VERSION = 2
          MARKER_PREFIX  = "// sjui:hotloader:begin"
          MARKER_BEGIN   = "#{MARKER_PREFIX} v#{REGION_VERSION} — generated by `sjui setup`; この行から end までは再生成されます"
          MARKER_END     = "// sjui:hotloader:end"
          # AppDelegate 側（v1 まで注入していた先）。v2 では**注入せず、剥がすだけ**。
          APP_LIFECYCLE_METHODS = %w[
            applicationDidBecomeActive applicationDidEnterBackground applicationWillTerminate
          ].freeze
          # SceneDelegate 側（v2 の注入先）
          SCENE_LIFECYCLE_METHODS = [
            ["sceneDidBecomeActive",   "true"],
            ["sceneDidEnterBackground", "false"],
            ["sceneDidDisconnect",      "false"],
          ].freeze
          IF_DEBUG_LINE   = /\A\s*#if DEBUG\s*\z/
          ENDIF_LINE      = /\A\s*#endif\s*\z/
          HOTLOADER_LINE  = /\A\s*HotLoader\.instance\.isHotLoadEnabled\s*=\s*(?:true|false)\s*\z/
          VIEWCREATOR_LINE = /\A\s*UIViewCreator\.(?:prepare|copyResourcesToDocuments)\(\)\s*\z/

          # 「この版の区間が在る」= 何もしなくてよい。版が違えば貼り直す。
          def current_region?(content)
            content.include?(MARKER_BEGIN)
          end

          def marker_block(code_lines, indent)
            ([MARKER_BEGIN] + code_lines + [MARKER_END]).map { |l| "#{indent}#{l}\n" }.join
          end

          def add_hotloader_content(content)
            # import文を追加
            unless content.include?("import SwiftJsonUI")
              content = content.gsub(/^import UIKit/, "import UIKit\nimport SwiftJsonUI")
            end

            # 前版の生成物を落とす。マーカー区間 → 旧生成物（行単位）の順。
            content = strip_generated_regions(content)
            stray = []
            content = strip_legacy_hotloader_lines(content, warnings: stray)
            stray.uniq.each do |line|
              puts "Warning: #{line} は生成節から離れた位置に在るので残しました。" \
                   "二重に実行されるなら手で 1 本消してください（実行順を勝手に変えないためです）。"
            end

            content = add_hotloader_to_did_finish_launching(content)
            # v2: `application*` には注入しない。v1 の区間を剥がした結果 空になった
            # 生成メソッドだけを畳む（本文が 1 行でも残っていれば残す）。
            # ⚠️ この畳み込みは v1 では冗長だった（剥がした直後に同じメソッドへ
            #   注入し直していたので最終形が同じ）。注入先を scene に移した v2 で
            #   初めて効く——「冗長」の判定は版に紐づく。
            content = remove_emptied_app_lifecycle_methods(content)

            content
          end

          # マーカー区間だけを行単位で落とす（区間外は 1 バイトも触らない）
          def strip_generated_regions(content)
            out = []
            inside = false
            content.each_line do |line|
              if line.include?(MARKER_PREFIX)
                inside = true
                next
              end
              if line.include?(MARKER_END)
                inside = false
                next
              end
              out << line unless inside
            end
            out.join
          end

          # マーカーが無い旧生成物: 生成した行だけを行単位で剥がす。
          # ⚠️ 以前はここが正規表現でメソッド本文ごと削除しており、
          #   (1) 生成節の後ろにユーザーが足した行を巻き込み、
          #   (2) HotLoader 以外の `#if DEBUG` を持つメソッドでは閉じ括弧を残さず消して
          #       brace が -1 になりビルドが壊れた（初回 setup で到達する）。
          #
          # `only_methods` を渡すと、そのメソッドの本文に在る三行組だけを剥がす。
          # scene 側で使う: v2 が注入するのは 3 本なので、**注入しないメソッドの
          # toggle を消すと消費側の挙動が黙って減る**（実測: 裸の三行組を 5 本持つ木が在り、
          # うち 2 本は v2 の注入先ではない）。
          #
          # `UIViewCreator.*` の単独行は、**三行組と連続しているときだけ**剥がす。
          # 実測: `prepare()` と `copyResourcesToDocuments()` が 13 行離れ、間に消費側の
          # 初期化が 12 行（ネットワーク / 外観 / Firebase / 通知登録）在る木がある。
          # 無条件に剥がして先頭へ貼り直すと、**消費側が選んだ実行順が無言で変わる**。
          # 離れている行は残し、警告で名指しする（二重の `prepare()` は diff に出るが、
          # 順序の消失は diff に出ない ⇒ 声の大きい失敗を選ぶ）。
          def strip_legacy_hotloader_lines(content, only_methods: nil, warnings: nil)
            lines = content.lines
            scope = method_scope(lines)
            generated = generated_line_indexes(lines, only_methods, scope)

            lines.each_with_index.reject { |line, i| generated.include?(i) }.each do |line, i|
              next unless line =~ VIEWCREATOR_LINE
              next unless only_methods.nil? || only_methods.include?(scope[i])

              (warnings ||= []) << line.strip
            end
            lines.each_with_index.reject { |_line, i| generated.include?(i) }.map(&:first).join
          end

          # 各行がどのメソッドの中に在るか
          def method_scope(lines)
            current = nil
            lines.map do |line|
              if (m = line.match(/\A\s*func\s+(\w+)/))
                current = m[1]
              end
              current
            end
          end

          # 「生成された行」= 三行組と、**それに連続する** UIViewCreator 行。
          # ⚠️ 2 パスにするのは、1 パスで「後から前の行を取り消す」形にすると、
          #   取り消した行の警告が消し忘れで残るため（実測で踏んだ: 連続しているのに
          #   「離れている」警告が出た）。生成行の index を先に確定させる。
          def generated_line_indexes(lines, only_methods, scope)
            generated = []
            i = 0
            while i < lines.length
              in_scope = only_methods.nil? || only_methods.include?(scope[i])
              unless in_scope && lines[i] =~ IF_DEBUG_LINE &&
                     lines[i + 1].to_s =~ HOTLOADER_LINE && lines[i + 2].to_s =~ ENDIF_LINE
                i += 1
                next
              end

              first = i
              first -= 1 while first.positive? && lines[first - 1] =~ VIEWCREATOR_LINE
              last = i + 2
              last += 1 while lines[last + 1].to_s =~ VIEWCREATOR_LINE
              generated.concat((first..last).to_a)
              i = last + 1
            end
            generated
          end

          # v1 の区間を剥がした結果、本文が空になった `application*` を畳む。
          # 本文に 1 行でも残っていれば消さない（消費側の処理を保つ）。
          def remove_emptied_app_lifecycle_methods(content)
            APP_LIFECYCLE_METHODS.each do |name|
              content = content.gsub(
                /^[ \t]*func\s+#{name}\s*\([^)]*\)\s*\{[ \t]*\n(?:[ \t]*\n)*[ \t]*\}[ \t]*\n(?:[ \t]*\n)?/,
                ""
              )
            end
            content
          end

          def add_hotloader_to_did_finish_launching(content)
            did_finish_pattern = /^([ \t]*)(func application\([^)]+didFinishLaunchingWithOptions[^{]*\{)[ \t]*\n/

            if (m = content.match(did_finish_pattern))
              body_indent = m[1] + "    "
              block = marker_block([
                "UIViewCreator.prepare()",
                "UIViewCreator.copyResourcesToDocuments()",
                "#if DEBUG",
                "HotLoader.instance.isHotLoadEnabled = true",
                "#endif",
              ], body_indent)
              content.sub(m[0], m[0] + block)
            else
              add_method_to_class_safely(content, generate_did_finish_launching_method)
            end
          end

          # 既にメソッドが在れば**本文を残したまま**先頭にマーカー区間を足す。
          # 無ければメソッドごと生成する。
          # ⚠️ 以前は「在れば何もしない」で、既存のライフサイクルメソッドを持つアプリでは
          #   HotLoader の on/off が黙って注入されないままだった。
          def ensure_lifecycle_block(content, method_name, enabled)
            pattern = /^([ \t]*)(func\s+#{method_name}\s*\([^)]*\)\s*\{)[ \t]*\n/
            if (m = content.match(pattern))
              block = marker_block(["#if DEBUG", "HotLoader.instance.isHotLoadEnabled = #{enabled}", "#endif"], m[1] + "    ")
              content.sub(m[0], m[0] + block)
            else
              add_method_to_class_safely(content, generate_lifecycle_method(method_name, enabled))
            end
          end

          def generate_lifecycle_method(method_name, enabled)
            <<~SWIFT.strip
              func #{method_name}(_ application: UIApplication) {
              #{marker_block(["#if DEBUG", "HotLoader.instance.isHotLoadEnabled = #{enabled}", "#endif"], "    ").chomp}
              }
            SWIFT
          end

          def generate_did_finish_launching_method
            <<~SWIFT.strip
              func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
              #{marker_block(["UIViewCreator.prepare()", "UIViewCreator.copyResourcesToDocuments()", "#if DEBUG", "HotLoader.instance.isHotLoadEnabled = true", "#endif"], "    ").chomp}
                  return true
              }
            SWIFT
          end

          # ── SceneDelegate 側（v2 の注入先）────────────────────────────────
          #
          # iOS 27 SDK は scene ライフサイクル必須で、`applicationDidBecomeActive`
          # などは呼ばれない。HotLoader の on/off をそこに置いたままにすると、
          # scene 化したアプリで**ホットリロードだけが黙って死ぬ**。
          SCENE_MISSING_WARNING =
            "Warning: SceneDelegate.swift が見つかりません。HotLoader の on/off を注入できません。" \
            "iOS 27 SDK では UIScene ライフサイクルが必須で、未採用のアプリは起動しません " \
            "(UIScene life cycle is required for apps built with this SDK)。" \
            "AppDelegate 側への注入には**戻しません**（戻すと scene 化後の再 setup で旧型に巻き戻ります）。"
          MANIFEST_MISSING_WARNING =
            "Warning: Info.plist に UIApplicationSceneManifest がありません。HotLoader の on/off を注入できません。" \
            "iOS 27 SDK では UIScene ライフサイクルが必須で、未採用のアプリは起動しません。" \
            "AppDelegate 側への注入には**戻しません**。"

          # 「注入が届いている」= scene 側にこの版の区間が在る。
          # ⚠️ 最初の実装は「SceneDelegate が無ければ最新扱い」で true を返していた。
          #   その結果、2 回目以降は早期 return で**警告が消え**、届いていないのに
          #   "already up to date" だけが出た——直そうとしている「成功の顔」そのもの。
          #   自分の腕（警告は毎回出る）が捕まえた。
          def scene_up_to_date?(project_dir)
            path = find_scene_delegate_file(project_dir)
            return false if path.nil? || !scene_manifest?(project_dir)

            current_region?(File.read(path))
          rescue StandardError
            false
          end

          def update_scene_delegate(project_dir)
            path = find_scene_delegate_file(project_dir)
            if path.nil?
              puts SCENE_MISSING_WARNING
              return nil
            end
            unless scene_manifest?(project_dir)
              puts MANIFEST_MISSING_WARNING
              return nil
            end

            content = File.read(path)
            unless content.include?("import SwiftJsonUI")
              content = content.gsub(/^import UIKit/, "import UIKit\nimport SwiftJsonUI")
            end
            content = strip_generated_regions(content)
            # v2 が注入する 3 本の中の裸の三行組だけを剥がす（重複注入を避ける）。
            # それ以外のメソッドが持つ toggle は**消さない**: 消すと消費側の挙動が
            # 黙って減る。代わりに名指しして、区間の外に在ることを伝える。
            targets = SCENE_LIFECYCLE_METHODS.map(&:first)
            outside = legacy_toggle_methods(content) - targets
            content = strip_legacy_hotloader_lines(content, only_methods: targets)
            unless outside.empty?
              puts "Note: #{outside.join(', ')} が持つ HotLoader の on/off は生成節の外なので残しました " \
                   "(sjui が管理するのは #{targets.join(', ')} の 3 本です)。"
            end
            SCENE_LIFECYCLE_METHODS.each do |name, enabled|
              content = ensure_scene_block(content, name, enabled)
            end
            File.write(path, content)
            puts "HotLoader lifecycle hooks written to SceneDelegate: #{path}"
            path
          end

          def find_scene_delegate_file(project_dir)
            files = Dir.glob("#{project_dir}/**/SceneDelegate.swift").reject do |path|
              ignored_path?(path) || path.include?("Tests") || path.include?("UITests")
            end
            files.min_by { |path| path.split("/").length }
          end

          # scene 採用の宣言源は **2 つ**ある。
          #
          # ⚠️ 最初の実装は Info.plist の鍵しか見ておらず、実測で消費側 2 面のうち
          #   1 面は plist に鍵を 0 個しか持たない。Xcode が
          #   `GENERATE_INFOPLIST_FILE = YES` で plist を生成する構成では、宣言は
          #   **pbxproj のビルド設定**に在る。当方の fixture が plist で宣言していたので
          #   腕は全部緑のまま、実在のプロジェクトには一度も届かない修正になっていた。
          #
          #   走査根から build / Pods / SourcePackages / DerivedData を除いた実測
          #   (2026-09-14)。分母は**構成の綴り**で書く（面の名前は配布物に入れない）:
          #     `jui.config.json` が ios を宣言する木（2 本）
          #         Info.plist 3 本中 鍵を持つもの 0 / pbxproj に 12 行（全て [sdk=…] 付き）
          #     `sjui.config.json` だけを持ち sjui_tools を直に使う木（1 本）
          #         Info.plist 3 本中 鍵を持つもの 3 / pbxproj に 0 行
          #   ⇒ **どちらの源も実在する**。片方だけ見る述語はどちらかの木で必ず外す。
          #
          # 綴りは `[sdk=iphoneos*]` のような条件 suffix が付く形が実在する（面 A は
          # 全行が suffix 付き）。suffix 無しの綴りも Xcode は書くので、両方受ける。
          # `= YES` だけを受ける: `= NO` は「生成しない」宣言で、scene 非採用の側。
          SCENE_MANIFEST_KEY = "UIApplicationSceneManifest"
          SCENE_MANIFEST_BUILD_SETTING =
            /INFOPLIST_KEY_UIApplicationSceneManifest_Generation(?:\[[^\]]*\])?"?\s*=\s*YES/

          def scene_manifest?(project_dir)
            return true if info_plist_declares_scene?(project_dir)

            pbxproj_declares_scene?(project_dir)
          end

          # ⚠️ **全部読む**。最短パスの 1 本だけを読む形（`min_by`）だと、同じ深さの
          #   plist が複数在るときに実装依存の 1 本が選ばれる。実測 (2026-09-14):
          #   plist を生成する構成の木は `plists/{dev,staging,production}/Info.plist` の
          #   3 本が**全部同じ深さ**、plist を保持する構成の木も 3 本が同じ深さ。
          #   今日はどちらの木も 3 本が同じ答えなので症状は出ないが、1 本だけが鍵を持つ
          #   構成では**走るたびに答えが変わりうる**（同着の順序は保証されない）。
          def info_plist_declares_scene?(project_dir)
            Dir.glob("#{project_dir}/**/Info.plist")
               .reject { |path| ignored_path?(path) }
               .any? { |path| File.read(path).include?(SCENE_MANIFEST_KEY) }
          rescue StandardError
            false
          end

          def pbxproj_declares_scene?(project_dir)
            candidates = [@project_file_path]
            candidates << File.join(@project_file_path, "project.pbxproj") unless @project_file_path.end_with?(".pbxproj")
            candidates += Dir.glob("#{project_dir}/**/project.pbxproj").reject { |path| ignored_path?(path) }
            candidates.each do |path|
              next unless path && File.file?(path)
              return true if File.read(path) =~ SCENE_MANIFEST_BUILD_SETTING
            end
            false
          rescue StandardError
            false
          end

          def ignored_path?(path)
            path.include?("DerivedData") || path.include?("/build/") || path.include?("Pods") ||
              path.include?("Carthage") || path.include?(".build") || path.include?("node_modules") ||
              path.include?("SourcePackages")
          end

          # 裸の三行組を持つメソッド名を数える（区間の中は数えない）。
          def legacy_toggle_methods(content)
            lines = content.lines
            found = []
            current = nil
            lines.each_with_index do |line, i|
              if (m = line.match(/\A\s*func\s+(\w+)/))
                current = m[1]
              end
              next unless line =~ IF_DEBUG_LINE && lines[i + 1].to_s =~ HOTLOADER_LINE && lines[i + 2].to_s =~ ENDIF_LINE

              found << current if current
            end
            found.uniq
          end

          # Note は stdout だけなので、撃った人以外に痕跡が残らない。
          # **生成区間の中**に 1 行書いて、次に開いた人が読めるようにする
          # （区間の中なので「区間外不可侵」とは衝突しない）。
          #
          # ⚠️ 行番号を**単独の判別子にしない**。区間は `sjui setup` を撃ったときにしか
          #   再生成されないので、その間の消費側の編集にコメントは追随しない。
          #   `<file>:<line>` だけ書くと、相手が 1 行足した瞬間に**指し先がずれた嘘**になる。
          #   ⇒ 書くのは **ファイル名 ＋ 綴り（その行の実テキスト）＋ 観測した版と日付**。
          #   綴りは行移動に強く（grep で追える）、日付つきなら、消えていても
          #   「嘘」ではなく「その時点ではそうだった」になる。
          def annotate_generated_region(path, wiring)
            return if path.nil? || wiring.empty?

            note = "// sjui: #{WIRING_HEADLINE} —— #{wiring_fields(wiring)} " \
                   "[#{wiring_provenance}。有効化が 2 系統になります。" \
                   "行番号はこの時点の値で、以後の編集には追随しません]"
            content = File.read(path)
            return if content.include?(WIRING_HEADLINE)

            marked = content.sub(/^([ \t]*)#{Regexp.escape(MARKER_BEGIN)}[ \t]*\n/) { "#{Regexp.last_match(0)}#{Regexp.last_match(1)}#{note}\n" }
            File.write(path, marked)
          end

          def setup_version
            require_relative "../../../cli/version"
            "sjui #{SjuiTools::CLI::VERSION}"
          rescue StandardError, LoadError
            "sjui setup"
          end

          def observation_date
            Time.now.strftime("%Y-%m-%d")
          end

          def ensure_scene_block(content, method_name, enabled)
            pattern = /^([ \t]*)(func\s+#{method_name}\s*\([^)]*\)[^{]*\{)[ \t]*\n/
            if (m = content.match(pattern))
              block = marker_block(["#if DEBUG", "HotLoader.instance.isHotLoadEnabled = #{enabled}", "#endif"], m[1] + "    ")
              content.sub(m[0], m[0] + block)
            else
              add_method_to_class_safely(content, generate_scene_method(method_name, enabled))
            end
          end

          def generate_scene_method(method_name, enabled)
            arg = method_name == "sceneDidDisconnect" ? "_ scene: UIScene" : "_ scene: UIScene"
            <<~SWIFT.strip
              func #{method_name}(#{arg}) {
              #{marker_block(["#if DEBUG", "HotLoader.instance.isHotLoadEnabled = #{enabled}", "#endif"], "    ").chomp}
              }
            SWIFT
          end

          def add_method_to_class_safely(content, method_code)
            # より安全なアプローチ：クラスの最後の行を見つけて追加
            lines = content.lines
            
            # 最後の非空行のインデックスを見つける
            last_content_index = -1
            lines.reverse_each.with_index do |line, reverse_index|
              if line.strip.length > 0
                last_content_index = lines.length - 1 - reverse_index
                break
              end
            end
            
            # クラスの終端 } を見つける
            class_end_index = nil
            (last_content_index..lines.length-1).each do |i|
              if lines[i] && lines[i].strip == "}"
                class_end_index = i
                break
              end
            end
            
            if class_end_index
              # メソッドを正しいインデントで整形
              formatted_lines = []
              method_code.lines.each do |line|
                if line.strip.empty?
                  formatted_lines << ""
                else
                  formatted_lines << "    #{line.chomp}"
                end
              end
              formatted_lines << ""  # 1行の空行のみ
              
              # クラス終端の前に挿入
              formatted_lines.reverse_each do |formatted_line|
                lines.insert(class_end_index, "#{formatted_line}\n")
              end
              
              lines.join
            else
              # クラス終端が見つからない場合はそのまま返す
              content
            end
          end
        end
      end
    end
  end
end

# コマンドライン実行
if __FILE__ == $0
  if ARGV.length != 1
    puts "Usage: ruby app_delegate_setup.rb <project_file_path>"
    puts "Example: ruby app_delegate_setup.rb /path/to/project.pbxproj"
    exit 1
  end

  project_file_path = ARGV[0]
  
  begin
    setup = SjuiTools::UIKit::XcodeProject::Setup::AppDelegateSetup.new(project_file_path)
    setup.add_hotloader_functionality
  rescue => e
    puts "Error: #{e.message}"
    exit 1
  end
end