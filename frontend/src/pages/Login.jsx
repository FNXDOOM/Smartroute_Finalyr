import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Compass, LogIn } from 'lucide-react';
import { authAPI } from '../services/api';

const Login = () => {
  const [isLogin, setIsLogin] = useState(true);
  const [formData, setFormData] = useState({ email: '', password: '', name: '' });
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);
    try {
      if (isLogin) {
        const res = await authAPI.login({ email: formData.email, password: formData.password });
        if (res.data && res.data.token) {
          localStorage.setItem('token', res.data.token);
        }
        navigate('/dashboard');
      } else {
        await authAPI.register({ name: formData.name, email: formData.email, password_hash: formData.password });
        setFormData({ email: formData.email, password: '', name: '' });
        setIsLogin(true);
        setError(''); // clear any errors
        alert('Account created! Please log in.');
      }
    } catch (err) {
      const msg = err?.response?.data?.detail || 'Something went wrong. Please try again.';
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg-base)' }}>
      <div className="glass-panel animate-fade-in" style={{ padding: '3rem', width: '100%', maxWidth: '400px' }}>
        
        <div className="flex justify-center" style={{ marginBottom: '2rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Compass className="text-primary" size={32} />
            <span className="font-bold text-xl tracking-tight">Smart<span className="text-gradient">Route</span>AI</span>
          </div>
        </div>

        <h2 className="text-xl font-bold text-center" style={{ marginBottom: '1.5rem' }}>
          {isLogin ? 'Welcome Back' : 'Create an Account'}
        </h2>

        <form onSubmit={handleSubmit}>
          {error && (
            <div style={{ background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.4)', borderRadius: 'var(--radius-md)', padding: '0.75rem 1rem', marginBottom: '1rem', color: '#fca5a5', fontSize: '0.875rem' }}>
              {error}
            </div>
          )}
          {!isLogin && (
            <div className="input-group">
              <label className="input-label">Full Name</label>
              <input 
                type="text" 
                className="input-field" 
                placeholder="John Doe"
                value={formData.name}
                onChange={e => setFormData({...formData, name: e.target.value})}
                required={!isLogin}
              />
            </div>
          )}

          <div className="input-group">
            <label className="input-label">Email Address</label>
            <input 
              type="email" 
              className="input-field" 
              placeholder="name@example.com"
              value={formData.email}
              onChange={e => setFormData({...formData, email: e.target.value})}
              required
            />
          </div>

          <div className="input-group">
            <label className="input-label">Password</label>
            <input 
              type="password" 
              className="input-field" 
              placeholder="••••••••"
              value={formData.password}
              onChange={e => setFormData({...formData, password: e.target.value})}
              required
            />
          </div>

          <button type="submit" className="btn btn-primary" disabled={isLoading} style={{ width: '100%', marginTop: '1rem' }}>
            {isLoading ? 'Please wait...' : (isLogin ? 'Log In' : 'Sign Up')} <LogIn size={18} />
          </button>
        </form>

        <p className="text-center text-sm text-secondary" style={{ marginTop: '1.5rem' }}>
          {isLogin ? "Don't have an account? " : "Already have an account? "}
          <button 
            type="button"
            onClick={() => setIsLogin(!isLogin)}
            style={{ background: 'none', border: 'none', color: 'var(--primary)', fontWeight: '600', padding: 0 }}
          >
            {isLogin ? 'Sign up' : 'Log in'}
          </button>
        </p>

        <div style={{ marginTop: '2rem', textAlign: 'center' }}>
          <Link to="/" className="text-sm text-secondary hover:text-primary">← Back to Home</Link>
        </div>
      </div>
    </div>
  );
};

export default Login;
