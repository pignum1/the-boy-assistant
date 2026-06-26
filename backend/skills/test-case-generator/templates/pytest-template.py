"""pytest 模板 — async + fixtures + parametrize"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient

# ---- Fixtures ----

@pytest.fixture
async def db_session():
    """异步数据库 session fixture"""
    # 使用测试数据库
    async with async_session() as session:
        yield session
        await session.rollback()

@pytest.fixture
def sample_data():
    """测试数据 fixture"""
    return {
        "name": "测试数据",
        "status": "active",
    }

# ---- 正常路径测试 ----

@pytest.mark.asyncio
async def test_create_item_success(db_session, sample_data):
    """测试: 正常创建 item"""
    # Arrange
    service = ItemService(db_session)

    # Act
    result = await service.create(sample_data)

    # Assert
    assert result is not None
    assert result.name == "测试数据"
    assert result.id is not None

# ---- 参数化测试 ----

@pytest.mark.asyncio
@pytest.mark.parametrize("status,expected_valid", [
    ("active", True),
    ("inactive", True),
    ("deleted", False),
    ("invalid", False),
])
async def test_status_validation(db_session, status, expected_valid):
    """测试: 不同 status 值的校验"""
    service = ItemService(db_session)
    data = {"name": "test", "status": status}

    if expected_valid:
        result = await service.create(data)
        assert result.status == status
    else:
        with pytest.raises(ValueError):
            await service.create(data)

# ---- 边界值测试 ----

@pytest.mark.asyncio
async def test_create_item_name_too_long(db_session):
    """测试: 名称超过最大长度"""
    service = ItemService(db_session)
    data = {"name": "x" * 300}

    with pytest.raises(ValueError, match="名称过长"):
        await service.create(data)

# ---- Mock 外部依赖 ----

@pytest.mark.asyncio
async def test_create_item_with_external_call(db_session):
    """测试: 涉及外部 API 调用的场景"""
    with patch("app.services.item_service.external_api") as mock_api:
        mock_api.call = AsyncMock(return_value={"success": True})

        service = ItemService(db_session)
        result = await service.create_with_notification({"name": "test"})

        mock_api.call.assert_called_once()
        assert result is not None
