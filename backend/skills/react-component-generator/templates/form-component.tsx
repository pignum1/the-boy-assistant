import { useState, useCallback } from 'react';

interface FormField {
  name: string;
  label: string;
  type: 'text' | 'email' | 'password' | 'select';
  required?: boolean;
  options?: { value: string; label: string }[];
}

interface FormProps {
  fields: FormField[];
  initialValues?: Record<string, string>;
  onSubmit: (values: Record<string, string>) => Promise<void>;
  onCancel?: () => void;
}

export function FormComponent({
  fields,
  initialValues = {},
  onSubmit,
  onCancel,
}: FormProps) {
  const [values, setValues] = useState<Record<string, string>>(initialValues);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};
    for (const field of fields) {
      if (field.required && !values[field.name]?.trim()) {
        newErrors[field.name] = `${field.label} 不能为空`;
      }
      if (field.type === 'email' && values[field.name]) {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(values[field.name])) {
          newErrors[field.name] = '邮箱格式不正确';
        }
      }
    }
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async () => {
    if (!validate()) return;
    setSubmitting(true);
    try {
      await onSubmit(values);
    } catch (e: any) {
      setErrors({ _form: e?.message || '提交失败' });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ maxWidth: 600 }}>
      {fields.map((field) => (
        <div key={field.name} style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-dim)', marginBottom: 4 }}>
            {field.label}{field.required && <span style={{ color: 'var(--red-400)' }}> *</span>}
          </label>
          {field.type === 'select' ? (
            <select
              value={values[field.name] || ''}
              onChange={(e) => setValues({ ...values, [field.name]: e.target.value })}
              style={{ width: '100%', padding: 8, borderRadius: 8, border: '1px solid var(--border-medium)', background: 'var(--bg-card)', color: 'var(--text-primary)' }}
            >
              <option value="">请选择</option>
              {field.options?.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          ) : (
            <input
              type={field.type}
              value={values[field.name] || ''}
              onChange={(e) => setValues({ ...values, [field.name]: e.target.value })}
              style={{
                width: '100%', padding: 8, borderRadius: 8,
                border: `1px solid ${errors[field.name] ? 'var(--red-400)' : 'var(--border-medium)'}`,
                background: 'var(--bg-card)', color: 'var(--text-primary)', fontSize: 13, outline: 'none',
              }}
            />
          )}
          {errors[field.name] && <div style={{ fontSize: 11, color: 'var(--red-400)', marginTop: 4 }}>{errors[field.name]}</div>}
        </div>
      ))}
      <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 24 }}>
        {onCancel && <button onClick={onCancel} style={{ padding: '8px 20px', borderRadius: 8, border: '1px solid var(--border-medium)', background: 'var(--bg-card)', color: 'var(--text-secondary)', cursor: 'pointer' }}>取消</button>}
        <button onClick={handleSubmit} disabled={submitting} style={{ padding: '8px 20px', borderRadius: 8, border: 'none', background: 'var(--blue-400)', color: '#fff', cursor: 'pointer', fontWeight: 600 }}>{submitting ? '提交中...' : '保存'}</button>
      </div>
    </div>
  );
}
