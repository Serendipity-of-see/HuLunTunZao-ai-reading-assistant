from agents.parse_agent import split_chapters, split_sentences, parse_book


def test_split_sentences_basic():
    text = "他推开门。酒馆里喧嚣扑面。B坐在角落里，一言不发。"
    result = split_sentences(text)
    assert len(result) == 3
    assert "他推开门。" in result[0]


def test_split_sentences_dialogue_merge():
    text = '张三说："你怎么来了？"李四没有回答。'
    result = split_sentences(text)
    # The implementation correctly keeps the quoted dialogue with its speech verb.
    # Since ?" doesn't trigger a split (the " is in the negative lookahead),
    # the result is one merged unit: the speech + quoted content + following sentence.
    assert len(result) == 1
    assert "张三说" in result[0] and "你怎么来了" in result[0] and "李四没有回答" in result[0]


def test_split_chapters():
    text = "第一章 开始\n正文内容。\n第二章 继续\n更多内容。"
    result = split_chapters(text)
    assert len(result) == 2
    assert "第一章" in result[0][0]
    assert "第二章" in result[1][0]
