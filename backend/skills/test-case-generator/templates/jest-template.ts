// Jest 模板 — describe/it + mock + hooks

describe('ComponentName', () => {
  // ---- Hooks ----

  beforeEach(() => {
    jest.clearAllMocks();
  });

  // ---- 正常路径 ----

  it('should render correctly', () => {
    const { container } = render(<ComponentName />);
    expect(container).toBeInTheDocument();
  });

  it('should handle click action', async () => {
    const onClick = jest.fn();
    render(<ComponentName onClick={onClick} />);

    const button = screen.getByRole('button', { name: /submit/i });
    fireEvent.click(button);

    expect(onClick).toHaveBeenCalledTimes(1);
    expect(onClick).toHaveBeenCalledWith(expect.objectContaining({
      // expected args
    }));
  });

  // ---- Loading 状态 ----

  it('should show loading state', () => {
    render(<ComponentName loading={true} />);
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  // ---- Empty 状态 ----

  it('should show empty state', () => {
    render(<ComponentName items={[]} />);
    expect(screen.getByText(/暂无数据/i)).toBeInTheDocument();
  });

  // ---- Error 状态 ----

  it('should show error and retry', async () => {
    const onRetry = jest.fn();
    render(<ComponentName error="加载失败" onRetry={onRetry} />);

    expect(screen.getByText(/加载失败/i)).toBeInTheDocument();

    const retryBtn = screen.getByRole('button', { name: /重试/i });
    fireEvent.click(retryBtn);
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  // ---- Mock API ----

  it('should fetch data on mount', async () => {
    const mockData = [{ id: '1', name: 'Test' }];
    (api.get as jest.Mock).mockResolvedValue(mockData);

    render(<ComponentName />);

    await waitFor(() => {
      expect(screen.getByText('Test')).toBeInTheDocument();
    });
  });
});
