export interface ParserItem {
    vendor: string
    device_type: string
    class_name: string
    template_name: string
    description?: string
}

export interface TemplateItem {
    name: string
    group: string
    size: number
}

export interface TemplateRow extends TemplateItem {
    parsers: ParserItem[]
}

/** 消费者条目：解析器产出的键 → 实际消费它的 Saver */
export interface ParserConsumer {
    key: string
    saver: string
}

/**
 * 单个解析器的映射关系（`GET /api/parsers/mapping/` 的 parsers 元素）。
 * 前四个字段与 ParserItem 同义同型，故 extends 复用。
 */
export interface ParserMappingItem extends ParserItem {
    template_exists: boolean
    provides_keys: string[]
    template_keys: string[]
    keys_match: boolean
    has_dynamic_group_names: boolean
    consumers: ParserConsumer[]
    unconsumed_keys: string[]
}

/** 契约缺口：Saver 消费了某个键，但没有任何解析器产出它 */
export interface MissingProducer {
    device_type: string
    key: string
    saver: string
    note: string
}

/** 顶部统计汇总 */
export interface MappingSummary {
    parser_count: number
    saver_count: number
    keys_mismatch: number
    missing_producer_count: number
    unconsumed_count: number
}

/** GET /api/parsers/mapping/ 的响应结构 */
export interface MappingResult {
    summary: MappingSummary
    parsers: ParserMappingItem[]
    missing_producers: MissingProducer[]
}

/** 统计卡片视图模型：level 决定异常计数的配色 */
export interface StatCard {
    label: string
    value: number
    hint: string
    level: 'normal' | 'warning' | 'danger'
}