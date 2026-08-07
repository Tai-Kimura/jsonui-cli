# frozen_string_literal: true

module KjuiTools
  module Compose
    module Helpers
      class ImportManager
        def self.get_imports_map(package_name = nil)
          # Use provided package name or default to sample app
          pkg_name = package_name || 'com.example.kotlinjsonui.sample'

          {
            lazy_column: "import androidx.compose.foundation.lazy.LazyColumn",
            lazy_row: "import androidx.compose.foundation.lazy.LazyRow",
            background: "import androidx.compose.foundation.background",
            border: "import androidx.compose.foundation.border",
            shape: ["import androidx.compose.foundation.shape.RoundedCornerShape",
                    "import androidx.compose.ui.draw.clip",
                    "import androidx.compose.ui.draw.clipToBounds"],
            # Used when a border or shadow modifier renders without an
            # accompanying `cornerRadius` — `RectangleShape` lives in a
            # different package than `RoundedCornerShape`, so registering
            # `:shape` alone is not enough.
            rectangle_shape: "import androidx.compose.ui.graphics.RectangleShape",
            text_align: "import androidx.compose.ui.text.style.TextAlign",
            text_overflow: "import androidx.compose.ui.text.style.TextOverflow",
            text_auto_size: "import androidx.compose.foundation.text.TextAutoSize",
            text_style: "import androidx.compose.ui.text.TextStyle",
            local_text_style: "import androidx.compose.material3.LocalTextStyle",
            font_weight: "import androidx.compose.ui.text.font.FontWeight",
            font_family: ["import androidx.compose.ui.text.font.Font",
                          "import androidx.compose.ui.text.font.FontFamily"],
            font_style: "import androidx.compose.ui.text.font.FontStyle",
            font_spec: ["import com.kotlinjsonui.core.FontSpec",
                        "import com.kotlinjsonui.core.ResolvedFont"],
            text_unit: "import androidx.compose.ui.unit.TextUnit",
            visual_transformation: "import androidx.compose.ui.text.input.PasswordVisualTransformation",
            secure_text_field: ["import androidx.compose.material3.SecureTextField",
                                "import androidx.compose.foundation.text.input.rememberTextFieldState"],
            text_field_state: ["import androidx.compose.foundation.text.input.rememberTextFieldState",
                               "import androidx.compose.foundation.text.input.TextFieldState"],
            shadow: "import androidx.compose.ui.draw.shadow",
            drop_shadow: ["import androidx.compose.ui.draw.dropShadow",
                          "import androidx.compose.ui.graphics.shadow.Shadow"],
            dp_offset: "import androidx.compose.ui.unit.DpOffset",
            scale: "import androidx.compose.ui.draw.scale",
            compose_key: "import androidx.compose.runtime.key",
            arrangement: "import androidx.compose.foundation.layout.Arrangement",
            absolute_offset: "import androidx.compose.foundation.layout.absoluteOffset",
            keyboard_type: ["import androidx.compose.foundation.text.KeyboardOptions",
                            "import androidx.compose.ui.text.input.KeyboardType"],
            keyboard_actions: "import androidx.compose.foundation.text.KeyboardActions",
            keyboard_capitalization: "import androidx.compose.ui.text.input.KeyboardCapitalization",
            focus_requester: ["import androidx.compose.ui.focus.FocusRequester",
                              "import androidx.compose.ui.focus.focusRequester"],
            focus_changed: "import androidx.compose.ui.focus.onFocusChanged",
            software_keyboard_controller: "import androidx.compose.ui.platform.LocalSoftwareKeyboardController",
            ime_action: "import androidx.compose.ui.text.input.ImeAction",
            ime_padding: "import androidx.compose.foundation.layout.imePadding",
            button_colors: "import androidx.compose.material3.ButtonDefaults",
            button_padding: "import androidx.compose.foundation.layout.PaddingValues",
            padding_values: "import androidx.compose.foundation.layout.PaddingValues",
            text_decoration: "import androidx.compose.ui.text.style.TextDecoration",
            # `contentInsetAdjustmentBehavior` — the safe-area inset a
            # LazyColumn/LazyRow takes as contentPadding (plan 49 lane C).
            window_insets: ["import androidx.compose.foundation.layout.WindowInsets",
                            "import androidx.compose.foundation.layout.safeDrawing",
                            "import androidx.compose.foundation.layout.asPaddingValues"],
            window_insets_sides: ["import androidx.compose.foundation.layout.WindowInsetsSides",
                                  "import androidx.compose.foundation.layout.only"],
            # `Dp.Infinity` — the unresolved value of a bound maxWidth/maxHeight
            # (a 0.dp cap would annihilate the view). Plan 49 lane C.
            dp_infinity: "import androidx.compose.ui.unit.Dp",
            # `safeAreaInsetPositions` on a plain node (plan 49 lane C).
            safe_area_padding: ["import androidx.compose.foundation.layout.systemBarsPadding",
                                "import androidx.compose.foundation.layout.statusBarsPadding",
                                "import androidx.compose.foundation.layout.navigationBarsPadding"],
            shadow_style: ["import androidx.compose.ui.text.TextStyle",
                           "import androidx.compose.ui.graphics.Shadow",
                           "import androidx.compose.ui.geometry.Offset"],
            switch_colors: "import androidx.compose.material3.SwitchDefaults",
            slider_colors: "import androidx.compose.material3.SliderDefaults",
            checkbox_colors: "import androidx.compose.material3.CheckboxDefaults",
            dropdown_menu: ["import androidx.compose.material3.DropdownMenu",
                            "import androidx.compose.material3.DropdownMenuItem",
                            "import androidx.compose.ui.res.painterResource",
                            "import androidx.compose.foundation.clickable"],
            outlined_text_field: "import androidx.compose.material3.OutlinedTextField",
            # `Icons.Filled.*` / `Icons.Outlined.*` are extension properties on
            # `Icons.Filled` / `Icons.Outlined`, so both the `Icons` object and the
            # per-style wildcard extension imports are required. painterResource
            # stays for the drawable-resource fallback path.
            icons: ["import androidx.compose.ui.res.painterResource",
                    "import androidx.compose.material.icons.Icons",
                    "import androidx.compose.material.icons.filled.*",
                    "import androidx.compose.material.icons.outlined.*"],
            # TabView tab icons (tabview_component): selected tabs emit
            # Icons.Filled.<Name>, unselected tabs Icons.Outlined.<Name>
            # (the Material convention the dynamic component also follows).
            material_icons: ["import androidx.compose.material.icons.Icons",
                             "import androidx.compose.material.icons.filled.*",
                             "import androidx.compose.material.icons.outlined.*"],
            icon_button: "import androidx.compose.material3.IconButton",
            clickable: "import androidx.compose.foundation.clickable",
            # onLongPress Initial-pass detector (ModifierBuilder.build_long_pressable).
            # withTimeout / viewConfiguration / awaitPointerEvent are
            # AwaitPointerEventScope members — no import needed.
            long_press_gesture: ["import androidx.compose.foundation.gestures.awaitEachGesture",
                                 "import androidx.compose.foundation.gestures.awaitFirstDown",
                                 "import androidx.compose.ui.input.pointer.PointerEvent",
                                 "import androidx.compose.ui.input.pointer.PointerEventPass",
                                 "import androidx.compose.ui.input.pointer.PointerEventTimeoutCancellationException",
                                 "import androidx.compose.ui.input.pointer.pointerInput"],
            # onPan drag detector (ModifierBuilder.build_pannable).
            pan_gesture: ["import androidx.compose.foundation.gestures.detectDragGestures",
                          "import androidx.compose.ui.geometry.Offset",
                          "import androidx.compose.ui.input.pointer.pointerInput"],
            # onPinch zoom loop (ModifierBuilder.build_pinchable).
            # calculateZoom is a top-level function in foundation.gestures.
            pinch_gesture: ["import androidx.compose.foundation.gestures.awaitEachGesture",
                            "import androidx.compose.foundation.gestures.awaitFirstDown",
                            "import androidx.compose.foundation.gestures.calculateZoom",
                            "import androidx.compose.ui.input.pointer.PointerEvent",
                            "import androidx.compose.ui.input.pointer.pointerInput"],
            radio_colors: "import androidx.compose.material3.RadioButtonDefaults",
            async_image: "import coil3.compose.AsyncImage",
            image_request: "import coil3.request.ImageRequest",
            # Coil 3: headers live on NetworkHeaders, applied through the
            # `httpHeaders` extension on the request builder.
            network_headers: ["import coil3.network.NetworkHeaders",
                              "import coil3.network.httpHeaders"],
            content_scale: "import androidx.compose.ui.layout.ContentScale",
            lazy_grid: ["import androidx.compose.foundation.lazy.grid.LazyVerticalGrid",
                        "import androidx.compose.foundation.lazy.grid.LazyHorizontalGrid",
                        "import androidx.compose.foundation.lazy.grid.GridCells",
                        "import androidx.compose.ui.Alignment"],
            lazy_grid_state: "import androidx.compose.foundation.lazy.grid.rememberLazyGridState",
            horizontal_pager: ["import androidx.compose.foundation.pager.HorizontalPager",
                               "import androidx.compose.foundation.pager.rememberPagerState"],
            snapshot_flow: "import androidx.compose.runtime.snapshotFlow",
            # Button pressed-state colours (highlightBackground/highlightColor).
            pressed_state: ["import androidx.compose.foundation.interaction.MutableInteractionSource",
                            "import androidx.compose.foundation.interaction.collectIsPressedAsState",
                            "import androidx.compose.runtime.getValue",
                            "import androidx.compose.runtime.remember"],
            # ScrollView paging: per-item snap on the existing Lazy list.
            snap_fling: ["import androidx.compose.foundation.gestures.snapping.rememberSnapFlingBehavior",
                         "import androidx.compose.foundation.lazy.rememberLazyListState"],
            # ScrollView.defaultScrollAnchor without paging: the state alone.
            lazy_list_state: "import androidx.compose.foundation.lazy.rememberLazyListState",
            # The one-shot anchor scroll (suspend, item-agnostic).
            scroll_by: "import androidx.compose.foundation.gestures.scrollBy",
            color_manager: "import com.kotlinjsonui.generated.ColorManager",
            # Collection listStyle chrome — the shared library composable
            # both paths render (CollectionCellChrome).
            collection_cell_chrome: "import com.kotlinjsonui.components.CollectionCellChrome",
            material_theme: "import androidx.compose.material3.MaterialTheme",
            grid_item_span: "import androidx.compose.foundation.lazy.grid.GridItemSpan",
            webview: ["import android.webkit.WebView",
                      "import android.webkit.WebViewClient",
                      "import android.webkit.WebChromeClient",
                      "import androidx.compose.ui.viewinterop.AndroidView"],
            constraint_layout: ["import androidx.constraintlayout.compose.ConstraintLayout",
                                "import androidx.constraintlayout.compose.Dimension"],
            remember_state: ["import androidx.compose.runtime.remember",
                             "import androidx.compose.runtime.mutableStateOf",
                             "import androidx.compose.runtime.getValue",
                             "import androidx.compose.runtime.setValue"],
            remember: "import androidx.compose.runtime.remember",
            # The object face of underline/strikethrough with a declared
            # colour (text_component#decoration_color_expression): the native
            # TextDecoration cannot colour a line, so the shared library
            # device draws it from the captured TextLayoutResult.
            styled_text_lines: ["import com.kotlinjsonui.components.StyledLineState",
                                "import com.kotlinjsonui.components.styledTextLines"],
            graphics_layer: "import androidx.compose.ui.graphics.graphicsLayer",
            LaunchedEffect: "import androidx.compose.runtime.LaunchedEffect",
            launched_effect: "import androidx.compose.runtime.LaunchedEffect",
            disposable_effect: "import androidx.compose.runtime.DisposableEffect",
            alignment: "import androidx.compose.ui.Alignment",
            bias_alignment: "import androidx.compose.ui.BiasAlignment",
            circle_shape: "import androidx.compose.foundation.shape.CircleShape",
            alpha: "import androidx.compose.ui.draw.alpha",
            semantics: "import androidx.compose.ui.semantics.semantics",
            semantics_disabled: ["import androidx.compose.ui.semantics.semantics",
                                 "import androidx.compose.ui.semantics.disabled"],
            # userInteractionEnabled consumes events in the Initial pass.
            interaction_blocker: ["import androidx.compose.ui.input.pointer.PointerEventPass",
                                  "import androidx.compose.ui.input.pointer.pointerInput"],
            test_tag: "import androidx.compose.ui.platform.testTag",
            test_tags_as_resource_id: "import androidx.compose.ui.semantics.testTagsAsResourceId",
            image: "import androidx.compose.foundation.Image",
            color_filter: "import androidx.compose.ui.graphics.ColorFilter",
            local_content_color: "import androidx.compose.material3.LocalContentColor",
            painter_class: ["import androidx.compose.ui.graphics.painter.Painter",
                            "import androidx.compose.ui.geometry.Size",
                            "import androidx.compose.ui.graphics.drawscope.DrawScope"],
            local_context: "import androidx.compose.ui.platform.LocalContext",
            painter_resource: "import androidx.compose.ui.res.painterResource",
            string_resource: "import androidx.compose.ui.res.stringResource",
            color_resource: "import androidx.compose.ui.res.colorResource",
            r_class: "import #{pkg_name}.R",
            to_argb: "import androidx.compose.ui.graphics.toArgb",
            gradient: "import androidx.compose.ui.graphics.Brush",
            blur: "import androidx.compose.ui.draw.blur",
            navigation: ["import androidx.navigation.NavController",
                         "import androidx.navigation.compose.NavHost",
                         "import androidx.navigation.compose.composable",
                         "import androidx.navigation.compose.rememberNavController"],
            selectbox_component: "import com.kotlinjsonui.components.SelectBox",
            date_selectbox_component: "import com.kotlinjsonui.components.DateSelectBox",
            simple_date_selectbox_component: "import com.kotlinjsonui.components.SimpleDateSelectBox",
            visibility_wrapper: "import com.kotlinjsonui.components.VisibilityWrapper",
            custom_textfield: ["import com.kotlinjsonui.components.CustomTextField",
                               "import com.kotlinjsonui.components.CustomTextFieldWithMargins"],
            annotated_string: ["import androidx.compose.ui.text.AnnotatedString",
                               "import androidx.compose.ui.text.buildAnnotatedString",
                               "import androidx.compose.ui.text.SpanStyle",
                               "import androidx.compose.ui.text.withStyle"],
            link_annotation: "import androidx.compose.ui.text.LinkAnnotation",
            partial_attributes_text: ["import com.kotlinjsonui.components.PartialAttributesText",
                                      "import com.kotlinjsonui.components.PartialAttribute"],
            segment: "import com.kotlinjsonui.components.Segment",
            dynamic_mode_manager: "import com.kotlinjsonui.core.DynamicModeManager",
            configuration: "import com.kotlinjsonui.core.Configuration",
            safe_dynamic_view: "import com.kotlinjsonui.components.SafeDynamicView",
            circular_progress_indicator: "import androidx.compose.material3.CircularProgressIndicator",
            wrapContentSize: "import androidx.compose.foundation.layout.wrapContentSize",
            box: "import androidx.compose.foundation.layout.Box",
            DynamicView: "import com.kotlinjsonui.dynamic.DynamicView",
            JsonObject: "import com.google.gson.JsonObject",
            JsonParser: "import com.google.gson.JsonParser",
            dashed_border: ["import com.kotlinjsonui.dynamic.helpers.dashedBorder",
                            "import com.kotlinjsonui.dynamic.helpers.dottedBorder"],
            border_stroke: "import androidx.compose.foundation.BorderStroke",
            intrinsic_size: "import androidx.compose.foundation.layout.IntrinsicSize",
            distribution_fill: ["import com.kotlinjsonui.components.DistributionFillRow",
                                "import com.kotlinjsonui.components.DistributionFillColumn"],
            collection_stack: ["import com.kotlinjsonui.components.CollectionStack",
                               "import com.kotlinjsonui.components.CollectionStackMode",
                               "import com.kotlinjsonui.components.CollectionStackAxis"],
            safe_area_config: ["import com.kotlinjsonui.dynamic.LocalSafeAreaConfig",
                               "import com.kotlinjsonui.dynamic.SafeAreaConfig"],
            # EmbedContainer + friends live in the MAIN library module (not
            # `library-dynamic`). Static codegen emits `EmbedContainer(...)`
            # into every consumer GeneratedView, which has to compile in
            # release builds where the dynamic artifact isn't on the
            # classpath. KotlinJsonUI >= 2.8.2 ships these at
            # com.kotlinjsonui.embed.*.
            embed_container: ["import com.kotlinjsonui.embed.EmbedContainer",
                              "import com.kotlinjsonui.embed.EmbedNavigationMode"],
            # Registered ONLY for navigationMode:"isolated" call sites (new in
            # KotlinJsonUI 2.12.0) — keeping it out of :embed_container keeps
            # delegate-mode generated files byte-identical AND makes isolated
            # output fail to compile against pre-2.12.0 libraries (the
            # version-skew guard).
            embed_isolated_navigation: "import com.kotlinjsonui.embed.EmbedIsolatedNavigation",
            # Child-side embed init-params wiring, emitted unconditionally at
            # the top of every GeneratedView body (no-op when the screen is
            # not embedded). New in KotlinJsonUI 2.13.0.
            drive_embed_init_params: "import com.kotlinjsonui.embed.DriveEmbedInitParams",
            # Screen identity beacon, emitted for SCREEN layouts only (never
            # cells or partials). New in KotlinJsonUI 2.15.0 — registering it
            # only at marked call sites keeps unmarked output byte-identical
            # and makes marked output fail to compile against an older
            # library (the version-skew guard).
            screen_marker: "import com.kotlinjsonui.core.ScreenMarker",
            embedded_event: "import com.kotlinjsonui.embed.EmbeddedEvent",
            viewmodel_compose: "import androidx.lifecycle.viewmodel.compose.viewModel",
            # `hiltViewModel(viewModelStoreOwner, key)` from
            # androidx.hilt:hilt-navigation-compose. Works for both
            # @HiltViewModel-annotated VMs (resolved via HiltViewModelFactory)
            # and plain no-arg VMs (fallback to NewInstanceFactory). Used by
            # EmbedComponent so child ViewModels load in Hilt projects without
            # NoSuchMethodException on missing no-arg ctor.
            hilt_viewmodel: "import androidx.hilt.navigation.compose.hiltViewModel",
            composition_local_provider: "import androidx.compose.runtime.CompositionLocalProvider",
            # Responsive branches read LocalWindowInfo.containerSize (pixels)
            # and convert to dp via LocalDensity — replaces the deprecated
            # LocalConfiguration.screenWidthDp / .orientation reads.
            local_window_info: ["import androidx.compose.ui.platform.LocalWindowInfo",
                                "import androidx.compose.ui.platform.LocalDensity"]
          }
        end

        def self.update_imports(content, required_imports)
          imports_map = get_imports_map

          required_imports.each do |import_key|
            import_lines = imports_map[import_key]
            next unless import_lines

            if import_lines.is_a?(Array)
              import_lines.each do |import_line|
                unless content.include?(import_line)
                  # Add import after the last import statement
                  if content =~ /^(import .+\n)+/m
                    last_import_end = $~.end(0)
                    content.insert(last_import_end, "#{import_line}\n")
                  end
                end
              end
            else
              unless content.include?(import_lines)
                # Add import after the last import statement
                if content =~ /^(import .+\n)+/m
                  last_import_end = $~.end(0)
                  content.insert(last_import_end, "#{import_lines}\n")
                end
              end
            end
          end

          content
        end
      end
    end
  end
end
