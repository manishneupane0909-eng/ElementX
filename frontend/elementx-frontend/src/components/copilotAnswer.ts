export interface AnswerDetail {
  text: string
  /** Indentation depth below the list item, starting at 1. */
  level: number
}

export interface AnswerItem {
  text: string
  details: AnswerDetail[]
}

export type AnswerBlock =
  | { kind: 'paragraph'; text: string }
  | { kind: 'list'; items: AnswerItem[] }

const ITEM = /^- (.*)$/
const INDENTED = /^(\s+)(\S.*)$/

/**
 * Splits a plain-text answer into paragraphs and "- " lists with indented detail lines, the
 * layout the stored-record readout uses. Only line breaks, the "- " marker and leading
 * indentation are interpreted; every other character is kept verbatim. Returns null when the text
 * has no top-level list, so it is shown exactly as written.
 */
export function parseAnswer(text: string): AnswerBlock[] | null {
  const lines = text.replace(/\r\n?/g, '\n').split('\n')
  if (!lines.some((line) => ITEM.test(line))) {
    return null
  }

  const blocks: AnswerBlock[] = []
  let paragraph: string[] = []
  let list: AnswerItem[] | null = null

  const closeParagraph = () => {
    if (paragraph.length > 0) blocks.push({ kind: 'paragraph', text: paragraph.join('\n') })
    paragraph = []
  }
  const closeList = () => {
    if (list && list.length > 0) blocks.push({ kind: 'list', items: list })
    list = null
  }

  for (const line of lines) {
    if (line.trim() === '') {
      closeParagraph()
      closeList()
      continue
    }
    const item = ITEM.exec(line)
    if (item) {
      closeParagraph()
      list ??= []
      list.push({ text: item[1], details: [] })
      continue
    }
    const indented = INDENTED.exec(line)
    const currentList: AnswerItem[] | null = list
    if (indented && currentList && currentList.length > 0) {
      const level = Math.max(1, Math.floor(indented[1].replace(/\t/g, '  ').length / 2))
      currentList[currentList.length - 1].details.push({ text: indented[2], level })
      continue
    }
    closeList()
    paragraph.push(line)
  }
  closeParagraph()
  closeList()
  return blocks
}
