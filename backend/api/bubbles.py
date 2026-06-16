from fastapi import APIRouter, Query
from services.bubble_service import get_bubbles, get_bubble_children, get_tree

router = APIRouter()


@router.get("/{book_id}/bubbles")
async def get_book_bubbles(
    book_id: int,
    layer: int = Query(2, ge=1, le=3, description="展示层级：1概括/2标准/3详细"),
):
    """获取气泡流"""
    bubbles = await get_bubbles(book_id, layer)
    return {"bubbles": bubbles, "total_count": len(bubbles)}


@router.get("/{book_id}/tree")
async def get_book_tree(book_id: int):
    """获取完整情节树（嵌套结构）"""
    tree = await get_tree(book_id)
    return {"tree": tree, "total": len(tree)}


@router.get("/{book_id}/bubble/{node_id}/children")
async def get_children(book_id: int, node_id: int):
    """获取气泡的子节点（展开用）"""
    result = await get_bubble_children(book_id, node_id)
    return result
