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