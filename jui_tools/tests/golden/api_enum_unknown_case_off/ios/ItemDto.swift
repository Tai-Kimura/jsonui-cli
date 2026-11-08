// ╔══════════════════════════════════════════════════════════════════╗
// ║  @generated AUTO-GENERATED FILE — DO NOT EDIT
// ║  Source:    spec.json#/components/schemas/Item
// ║  Generator: jui build (api model)
// ║  Any manual edits will be OVERWRITTEN on next generation.
// ║  LLM/Agent: you MUST NOT modify this file.
// ╚══════════════════════════════════════════════════════════════════╝
import Foundation

nonisolated struct ItemDto: Codable, Sendable, Equatable, Hashable {
    let id: String
    let kind: DeviceKind
    let optKind: DeviceKind?
    let nullKind: DeviceKind?
    let defaulted: LoginMethod?
    let inline: ItemInline
    let level: Level
    let severity: Severity?
    let kinds: [DeviceKind]
    let byName: [String: DeviceKind]?
    let inner: InnerDto?

    init(id: String, kind: DeviceKind, optKind: DeviceKind?, nullKind: DeviceKind?, defaulted: LoginMethod? = LoginMethod.appleId, inline: ItemInline, level: Level, severity: Severity?, kinds: [DeviceKind], byName: [String: DeviceKind]?, inner: InnerDto?) {
        self.id = id
        self.kind = kind
        self.optKind = optKind
        self.nullKind = nullKind
        self.defaulted = defaulted
        self.inline = inline
        self.level = level
        self.severity = severity
        self.kinds = kinds
        self.byName = byName
        self.inner = inner
    }

    enum CodingKeys: String, CodingKey {
        case id
        case kind
        case optKind
        case nullKind
        case defaulted
        case inline
        case level
        case severity
        case kinds
        case byName
        case inner
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try container.decode(String.self, forKey: .id)
        self.kind = try container.decode(DeviceKind.self, forKey: .kind)
        self.optKind = try container.decodeIfPresent(DeviceKind.self, forKey: .optKind)
        self.nullKind = try container.decodeIfPresent(DeviceKind.self, forKey: .nullKind)
        self.defaulted = try container.decodeIfPresent(LoginMethod.self, forKey: .defaulted) ?? LoginMethod.appleId
        self.inline = try container.decode(ItemInline.self, forKey: .inline)
        self.level = try container.decode(Level.self, forKey: .level)
        self.severity = try container.decodeIfPresent(Severity.self, forKey: .severity)
        self.kinds = try container.decode([DeviceKind].self, forKey: .kinds)
        self.byName = try container.decodeIfPresent([String: DeviceKind].self, forKey: .byName)
        self.inner = try container.decodeIfPresent(InnerDto.self, forKey: .inner)
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(self.id, forKey: .id)
        try container.encode(self.kind, forKey: .kind)
        try container.encodeIfPresent(self.optKind, forKey: .optKind)
        try container.encodeIfPresent(self.nullKind, forKey: .nullKind)
        try container.encodeIfPresent(self.defaulted, forKey: .defaulted)
        try container.encode(self.inline, forKey: .inline)
        try container.encode(self.level, forKey: .level)
        try container.encodeIfPresent(self.severity, forKey: .severity)
        try container.encode(self.kinds, forKey: .kinds)
        try container.encodeIfPresent(self.byName, forKey: .byName)
        try container.encodeIfPresent(self.inner, forKey: .inner)
    }

    func hash(into hasher: inout Hasher) {
        hasher.combine(id)
        hasher.combine(kind)
        hasher.combine(optKind)
        hasher.combine(nullKind)
        hasher.combine(defaulted)
        hasher.combine(inline)
        hasher.combine(level)
        hasher.combine(severity)
        hasher.combine(kinds)
        hasher.combine(inner)
        // Omitted from hash (synthesis-incompatible types): byName
    }
}

// ══ END AUTO-GENERATED — DO NOT APPEND BELOW THIS LINE ══
