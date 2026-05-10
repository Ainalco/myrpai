import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'

// CSS Variables as constants
const colors = {
  hyperOrange: '#FF5722',
  espresso: '#3E2723',
  latte: '#795548',
  energyBurst: '#FFC107',
  goGreen: '#4CAF50',
  foam: '#FFF8E1',
  errorRed: '#F44336',
}

// Keyframe animations as style tag
const keyframes = `
  @keyframes slideIn {
    from {
      opacity: 0;
      transform: translateX(20px);
    }
    to {
      opacity: 1;
      transform: translateX(0);
    }
  }

  @keyframes bounce {
    0%, 100% { transform: translateY(0); }
    50% { transform: translateY(-10px); }
  }

  @keyframes celebrate {
    0% { transform: scale(0.8); opacity: 0; }
    50% { transform: scale(1.05); }
    100% { transform: scale(1); opacity: 1; }
  }

  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }
`

interface FormData {
  email: string
  firstName: string
  lastName: string
  password: string
  company: string
  teamSize: string
  currentCRM: string
  meetingTool: string
  meetingsPerWeek: string
  dealCycle: string
  challenge: string
}

interface FormErrors {
  [key: string]: string
}

const RegisterPage: React.FC = () => {
  const navigate = useNavigate()
  const { register: registerUser } = useAuth()
  const [currentStep, setCurrentStep] = useState(1)
  const [isLoading, setIsLoading] = useState(false)
  const [isSuccess, setIsSuccess] = useState(false)
  const [errors, setErrors] = useState<FormErrors>({})

  const [formData, setFormData] = useState<FormData>({
    email: '',
    firstName: '',
    lastName: '',
    password: '',
    company: '',
    teamSize: '',
    currentCRM: '',
    meetingTool: '',
    meetingsPerWeek: '',
    dealCycle: '',
    challenge: '',
  })

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
    // Clear error when user types
    if (errors[name]) {
      setErrors(prev => ({ ...prev, [name]: '' }))
    }
  }

  const validateStep = (step: number): boolean => {
    const newErrors: FormErrors = {}

    if (step === 1) {
      if (!formData.email) {
        newErrors.email = 'Please enter a valid work email'
      } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
        newErrors.email = 'Please enter a valid work email'
      }
      if (!formData.firstName) {
        newErrors.firstName = 'Please enter your first name'
      }
      if (!formData.lastName) {
        newErrors.lastName = 'Please enter your last name'
      }
      if (!formData.password) {
        newErrors.password = 'Password must be at least 8 characters'
      } else if (formData.password.length < 8) {
        newErrors.password = 'Password must be at least 8 characters'
      }
    }

    if (step === 2) {
      if (!formData.company) {
        newErrors.company = 'Please enter your company name'
      }
      if (!formData.teamSize) {
        newErrors.teamSize = 'Please select your team size'
      }
      if (!formData.currentCRM) {
        newErrors.currentCRM = 'Please select your CRM'
      }
      if (!formData.meetingTool) {
        newErrors.meetingTool = 'Please select your transcription tool'
      }
    }

    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const nextStep = () => {
    if (validateStep(currentStep)) {
      setCurrentStep(prev => prev + 1)
    }
  }

  const previousStep = () => {
    setCurrentStep(prev => prev - 1)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!validateStep(3)) return

    setIsLoading(true)

    try {
      const fullName = `${formData.firstName} ${formData.lastName}`.trim()

      await registerUser({
        email: formData.email,
        password: formData.password,
        full_name: fullName,
        company_name: formData.company || undefined,
        team_size: formData.teamSize || undefined,
        current_crm: formData.currentCRM || undefined,
        meeting_tool: formData.meetingTool || undefined,
        meetings_per_week: formData.meetingsPerWeek || undefined,
        deal_cycle: formData.dealCycle || undefined,
        challenge: formData.challenge || undefined,
      })

      setIsLoading(false)
      setIsSuccess(true)

      // Redirect after success
      setTimeout(() => navigate('/login'), 3000)
    } catch (err: any) {
      setIsLoading(false)
      setErrors({ submit: err.message || 'Registration failed. Please try again.' })
    }
  }

  // Styles
  const styles: { [key: string]: React.CSSProperties } = {
    body: {
      fontFamily: "'Inter', sans-serif",
      background: `linear-gradient(135deg, #FFFFFF 0%, ${colors.foam} 50%, #FFFFFF 100%)`,
      color: colors.espresso,
      lineHeight: 1.6,
      minHeight: '100vh',
    },
    nav: {
      background: 'white',
      boxShadow: `0 2px 10px rgba(62, 39, 35, 0.1)`,
      position: 'sticky' as const,
      top: 0,
      zIndex: 100,
    },
    navContainer: {
      maxWidth: 1400,
      margin: '0 auto',
      padding: '1rem 2rem',
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
    },
    logo: {
      fontFamily: "'Fredoka', cursive",
      fontSize: 32,
      fontWeight: 600,
      background: `linear-gradient(135deg, ${colors.hyperOrange} 0%, ${colors.espresso} 100%)`,
      WebkitBackgroundClip: 'text',
      WebkitTextFillColor: 'transparent',
      backgroundClip: 'text',
      letterSpacing: -0.5,
      textDecoration: 'none',
      display: 'inline-block',
    },
    navText: {
      color: colors.latte,
      fontSize: '0.875rem',
    },
    navLink: {
      color: colors.hyperOrange,
      textDecoration: 'none',
      fontWeight: 600,
    },
    signupContainer: {
      maxWidth: 1200,
      margin: '3rem auto',
      padding: '0 2rem',
      display: 'grid',
      gridTemplateColumns: '1fr 1fr',
      gap: '4rem',
      alignItems: 'start',
    },
    formSection: {
      background: 'white',
      borderRadius: 20,
      padding: '2.5rem',
      boxShadow: `0 10px 30px rgba(62, 39, 35, 0.1)`,
      position: 'relative' as const,
      overflow: 'hidden',
    },
    formSectionBefore: {
      content: '""',
      position: 'absolute' as const,
      top: 0,
      left: 0,
      right: 0,
      height: 5,
      background: `linear-gradient(90deg, ${colors.hyperOrange} 0%, ${colors.energyBurst} 50%, ${colors.goGreen} 100%)`,
    },
    formHeader: {
      textAlign: 'center' as const,
      marginBottom: '2rem',
    },
    h1: {
      fontFamily: "'Baloo 2', cursive",
      fontSize: '2.5rem',
      fontWeight: 800,
      color: colors.espresso,
      marginBottom: '0.5rem',
      lineHeight: 1.1,
    },
    subheadline: {
      color: colors.latte,
      fontSize: '1rem',
    },
    progressSteps: {
      display: 'flex',
      justifyContent: 'space-between',
      marginBottom: '2rem',
      position: 'relative' as const,
    },
    progressLine: {
      content: '""',
      position: 'absolute' as const,
      top: 15,
      left: 0,
      right: 0,
      height: 2,
      background: colors.foam,
      zIndex: 0,
    },
    step: {
      background: 'white',
      position: 'relative' as const,
      zIndex: 1,
      textAlign: 'center' as const,
      flex: 1,
    },
    stepCircle: {
      width: 30,
      height: 30,
      borderRadius: '50%',
      background: 'white',
      border: `2px solid ${colors.foam}`,
      margin: '0 auto 0.5rem',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      fontWeight: 700,
      fontSize: '0.875rem',
      color: colors.latte,
      transition: 'all 0.3s',
    },
    stepCircleActive: {
      background: colors.hyperOrange,
      borderColor: colors.hyperOrange,
      color: 'white',
      transform: 'scale(1.1)',
    },
    stepCircleCompleted: {
      background: colors.goGreen,
      borderColor: colors.goGreen,
      color: 'white',
    },
    stepLabel: {
      fontSize: '0.75rem',
      color: colors.latte,
    },
    stepLabelActive: {
      color: colors.espresso,
      fontWeight: 600,
    },
    formStep: {
      animation: 'slideIn 0.3s ease',
    },
    formGroup: {
      marginBottom: '1.5rem',
    },
    label: {
      display: 'block',
      marginBottom: '0.5rem',
      color: colors.espresso,
      fontWeight: 600,
      fontSize: '0.875rem',
    },
    required: {
      color: colors.hyperOrange,
    },
    input: {
      width: '100%',
      padding: '0.875rem 1rem',
      border: `2px solid ${colors.foam}`,
      borderRadius: 10,
      fontSize: '1rem',
      transition: 'all 0.3s',
      fontFamily: "'Inter', sans-serif",
      outline: 'none',
      boxSizing: 'border-box' as const,
    },
    inputError: {
      borderColor: colors.errorRed,
    },
    inputFocus: {
      borderColor: colors.hyperOrange,
      boxShadow: `0 0 0 3px rgba(255, 87, 34, 0.1)`,
    },
    errorMessage: {
      color: colors.errorRed,
      fontSize: '0.75rem',
      marginTop: '0.25rem',
    },
    helperText: {
      fontSize: '0.75rem',
      color: colors.latte,
      marginTop: '0.25rem',
      fontStyle: 'italic',
    },
    buttonGroup: {
      display: 'flex',
      gap: '1rem',
      marginTop: '2rem',
    },
    btn: {
      padding: '0.875rem 2rem',
      borderRadius: 50,
      fontFamily: "'Baloo 2', cursive",
      fontWeight: 700,
      fontSize: '1rem',
      border: 'none',
      cursor: 'pointer',
      transition: 'all 0.3s',
      textDecoration: 'none',
      display: 'inline-block',
      textAlign: 'center' as const,
      flex: 1,
    },
    btnPrimary: {
      background: `linear-gradient(135deg, ${colors.hyperOrange}, #E64A19)`,
      color: 'white',
    },
    btnSecondary: {
      background: 'white',
      color: colors.latte,
      border: `2px solid ${colors.foam}`,
    },
    checklist: {
      background: colors.foam,
      borderRadius: 10,
      padding: '1rem',
      margin: '1.5rem 0',
    },
    checklistItem: {
      display: 'flex',
      alignItems: 'center',
      gap: '0.5rem',
      margin: '0.5rem 0',
      color: colors.espresso,
      fontSize: '0.875rem',
    },
    checkIcon: {
      color: colors.goGreen,
      flexShrink: 0,
    },
    heroSection: {
      padding: '2rem',
    },
    heroContent: {
      position: 'sticky' as const,
      top: 100,
    },
    squirrelWelcome: {
      background: 'white',
      borderRadius: 20,
      padding: '2rem',
      textAlign: 'center' as const,
      marginBottom: '2rem',
      boxShadow: `0 10px 30px rgba(62, 39, 35, 0.1)`,
      position: 'relative' as const,
      overflow: 'hidden',
    },
    squirrelIcon: {
      fontSize: '4rem',
      marginBottom: '1rem',
      animation: 'bounce 2s infinite',
      display: 'inline-block',
    },
    welcomeTitle: {
      fontFamily: "'Baloo 2', cursive",
      fontSize: '1.5rem',
      color: colors.espresso,
      marginBottom: '0.5rem',
    },
    welcomeText: {
      color: colors.latte,
      fontSize: '0.875rem',
      lineHeight: 1.5,
    },
    socialProof: {
      background: `linear-gradient(135deg, ${colors.foam} 0%, white 100%)`,
      borderRadius: 15,
      padding: '1.5rem',
      marginBottom: '1.5rem',
    },
    proofQuote: {
      fontStyle: 'italic',
      color: colors.espresso,
      marginBottom: '0.5rem',
      fontSize: '0.875rem',
      lineHeight: 1.5,
    },
    proofAuthor: {
      color: colors.latte,
      fontSize: '0.75rem',
      fontWeight: 600,
    },
    statsGrid: {
      display: 'grid',
      gridTemplateColumns: '1fr 1fr',
      gap: '1rem',
      marginTop: '1.5rem',
    },
    statCard: {
      background: 'white',
      padding: '1rem',
      borderRadius: 10,
      textAlign: 'center' as const,
      border: `2px solid ${colors.foam}`,
    },
    statNumber: {
      fontFamily: "'Baloo 2', cursive",
      fontSize: '1.5rem',
      color: colors.hyperOrange,
      fontWeight: 800,
    },
    statLabel: {
      fontSize: '0.75rem',
      color: colors.latte,
    },
    successContainer: {
      textAlign: 'center' as const,
      padding: '3rem',
      animation: 'celebrate 0.5s ease',
    },
    successIcon: {
      fontSize: '5rem',
      marginBottom: '1rem',
    },
    successTitle: {
      fontFamily: "'Baloo 2', cursive",
      fontSize: '2.5rem',
      color: colors.espresso,
      marginBottom: '1rem',
    },
    loading: {
      textAlign: 'center' as const,
      padding: '2rem',
    },
    spinner: {
      border: `3px solid ${colors.foam}`,
      borderTop: `3px solid ${colors.hyperOrange}`,
      borderRadius: '50%',
      width: 40,
      height: 40,
      animation: 'spin 1s linear infinite',
      margin: '0 auto',
    },
    loadingText: {
      marginTop: '1rem',
      color: colors.latte,
      fontStyle: 'italic',
    },
    trustBox: {
      marginTop: '1.5rem',
      padding: '1.5rem',
      background: 'white',
      borderRadius: 15,
      textAlign: 'center' as const,
    },
  }

  // Input focus state management
  const [focusedInput, setFocusedInput] = useState<string | null>(null)

  const getInputStyle = (name: string): React.CSSProperties => ({
    ...styles.input,
    ...(errors[name] ? styles.inputError : {}),
    ...(focusedInput === name ? styles.inputFocus : {}),
  })

  const getStepCircleStyle = (step: number): React.CSSProperties => ({
    ...styles.stepCircle,
    ...(currentStep === step ? styles.stepCircleActive : {}),
    ...(currentStep > step ? styles.stepCircleCompleted : {}),
  })

  const getStepLabelStyle = (step: number): React.CSSProperties => ({
    ...styles.stepLabel,
    ...(currentStep === step ? styles.stepLabelActive : {}),
  })

  // Success State
  if (isSuccess) {
    return (
      <div style={styles.body}>
        <style>{keyframes}</style>
        <nav style={styles.nav}>
          <div style={styles.navContainer}>
            <span style={styles.logo}>Scurry</span>
            <div style={styles.navText}>
              Already have an account? <Link to="/login" style={styles.navLink}>Log in →</Link>
            </div>
          </div>
        </nav>
        <div style={{ ...styles.signupContainer, gridTemplateColumns: '1fr' }}>
          <div style={styles.formSection}>
            <div style={styles.formSectionBefore} />
            <div style={styles.successContainer}>
              <div style={styles.successIcon}>🎉</div>
              <h2 style={styles.successTitle}>HOLY ACORNS! You're in!</h2>
              <p style={{ color: colors.latte, marginBottom: '2rem' }}>
                Check your email for next steps. We're so excited to have you!
              </p>
              <Link
                to="/login"
                style={{ ...styles.btn, ...styles.btnPrimary, maxWidth: 300, margin: '0 auto', display: 'block' }}
              >
                Go to Login →
              </Link>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div style={styles.body}>
      <style>{keyframes}</style>

      {/* Navigation */}
      <nav style={styles.nav}>
        <div style={styles.navContainer}>
          <span style={styles.logo}>Scurry</span>
          <div style={styles.navText}>
            Already have an account? <Link to="/login" style={styles.navLink}>Log in →</Link>
          </div>
        </div>
      </nav>

      {/* Main Container */}
      <div style={styles.signupContainer}>
        {/* Form Section */}
        <div style={styles.formSection}>
          <div style={styles.formSectionBefore} />

          <div style={styles.formHeader}>
            <h1 style={styles.h1}>Ready to Join the Scurry?</h1>
            <p style={styles.subheadline}>Join 100+ squirrels already gathering nuts automatically!</p>
          </div>

          {/* Progress Steps */}
          <div style={styles.progressSteps}>
            <div style={styles.progressLine} />
            <div style={styles.step}>
              <div style={getStepCircleStyle(1)}>1</div>
              <div style={getStepLabelStyle(1)}>Basic Info</div>
            </div>
            <div style={styles.step}>
              <div style={getStepCircleStyle(2)}>2</div>
              <div style={getStepLabelStyle(2)}>Your Forest</div>
            </div>
            <div style={styles.step}>
              <div style={getStepCircleStyle(3)}>3</div>
              <div style={getStepLabelStyle(3)}>Preferences</div>
            </div>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit}>
            {errors.submit && (
              <div style={{ ...styles.errorMessage, marginBottom: '1rem', textAlign: 'center' }}>
                {errors.submit}
              </div>
            )}

            {/* Step 1: Basic Info */}
            {currentStep === 1 && (
              <div style={styles.formStep}>
                <div style={styles.formGroup}>
                  <label style={styles.label}>
                    Where should we send your nuts? (Work Email) <span style={styles.required}>*</span>
                  </label>
                  <input
                    type="email"
                    name="email"
                    value={formData.email}
                    onChange={handleInputChange}
                    onFocus={() => setFocusedInput('email')}
                    onBlur={() => setFocusedInput(null)}
                    style={getInputStyle('email')}
                    placeholder="you@company.com"
                  />
                  {errors.email && <div style={styles.errorMessage}>{errors.email}</div>}
                  <div style={styles.helperText}>We'll send your login details and acorn updates here</div>
                </div>

                <div style={styles.formGroup}>
                  <label style={styles.label}>
                    First Name <span style={styles.required}>*</span>
                  </label>
                  <input
                    type="text"
                    name="firstName"
                    value={formData.firstName}
                    onChange={handleInputChange}
                    onFocus={() => setFocusedInput('firstName')}
                    onBlur={() => setFocusedInput(null)}
                    style={getInputStyle('firstName')}
                    placeholder="Speedy"
                  />
                  {errors.firstName && <div style={styles.errorMessage}>{errors.firstName}</div>}
                </div>

                <div style={styles.formGroup}>
                  <label style={styles.label}>
                    Last Name <span style={styles.required}>*</span>
                  </label>
                  <input
                    type="text"
                    name="lastName"
                    value={formData.lastName}
                    onChange={handleInputChange}
                    onFocus={() => setFocusedInput('lastName')}
                    onBlur={() => setFocusedInput(null)}
                    style={getInputStyle('lastName')}
                    placeholder="Squirrel"
                  />
                  {errors.lastName && <div style={styles.errorMessage}>{errors.lastName}</div>}
                </div>

                <div style={styles.formGroup}>
                  <label style={styles.label}>
                    Password <span style={styles.required}>*</span>
                  </label>
                  <input
                    type="password"
                    name="password"
                    value={formData.password}
                    onChange={handleInputChange}
                    onFocus={() => setFocusedInput('password')}
                    onBlur={() => setFocusedInput(null)}
                    style={getInputStyle('password')}
                    placeholder="Make it strong like coffee!"
                  />
                  {errors.password && <div style={styles.errorMessage}>{errors.password}</div>}
                  <div style={styles.helperText}>Must contain at least one nut emoji... kidding! 8+ characters will do</div>
                </div>

                <div style={styles.buttonGroup}>
                  <button
                    type="button"
                    onClick={nextStep}
                    style={{ ...styles.btn, ...styles.btnPrimary }}
                  >
                    Continue to Your Forest →
                  </button>
                </div>
              </div>
            )}

            {/* Step 2: Company Info */}
            {currentStep === 2 && (
              <div style={styles.formStep}>
                <div style={styles.formGroup}>
                  <label style={styles.label}>
                    Name of Your Tree (Company Name) <span style={styles.required}>*</span>
                  </label>
                  <input
                    type="text"
                    name="company"
                    value={formData.company}
                    onChange={handleInputChange}
                    onFocus={() => setFocusedInput('company')}
                    onBlur={() => setFocusedInput(null)}
                    style={getInputStyle('company')}
                    placeholder="Acorn Industries"
                  />
                  {errors.company && <div style={styles.errorMessage}>{errors.company}</div>}
                </div>

                <div style={styles.formGroup}>
                  <label style={styles.label}>
                    Team Size <span style={styles.required}>*</span>
                  </label>
                  <select
                    name="teamSize"
                    value={formData.teamSize}
                    onChange={handleInputChange}
                    onFocus={() => setFocusedInput('teamSize')}
                    onBlur={() => setFocusedInput(null)}
                    style={getInputStyle('teamSize')}
                  >
                    <option value="">Select your forest size</option>
                    <option value="1">Just me (lone squirrel)</option>
                    <option value="2-5">2-5 (small tree)</option>
                    <option value="6-20">6-20 (growing forest)</option>
                    <option value="21-50">21-50 (proper woods)</option>
                    <option value="50+">50+ (ancient forest)</option>
                  </select>
                  {errors.teamSize && <div style={styles.errorMessage}>{errors.teamSize}</div>}
                </div>

                <div style={styles.formGroup}>
                  <label style={styles.label}>
                    Current CRM <span style={styles.required}>*</span>
                  </label>
                  <select
                    name="currentCRM"
                    value={formData.currentCRM}
                    onChange={handleInputChange}
                    onFocus={() => setFocusedInput('currentCRM')}
                    onBlur={() => setFocusedInput(null)}
                    style={getInputStyle('currentCRM')}
                  >
                    <option value="">Select your CRM</option>
                    <option value="pipedrive">Pipedrive 🎯 (Native Integration!)</option>
                    <option value="hubspot">HubSpot</option>
                    <option value="salesforce">Salesforce</option>
                    <option value="zoho">Zoho CRM</option>
                    <option value="monday">Monday.com</option>
                    <option value="copper">Copper</option>
                    <option value="freshsales">Freshsales</option>
                    <option value="insightly">Insightly</option>
                    <option value="close">Close</option>
                    <option value="keap">Keap</option>
                    <option value="none">No CRM yet</option>
                    <option value="other">Other</option>
                  </select>
                  {errors.currentCRM && <div style={styles.errorMessage}>{errors.currentCRM}</div>}
                  <div style={styles.helperText}>Pipedrive users get our deepest integration!</div>
                </div>

                <div style={styles.formGroup}>
                  <label style={styles.label}>
                    Meeting Transcription Tool <span style={styles.required}>*</span>
                  </label>
                  <select
                    name="meetingTool"
                    value={formData.meetingTool}
                    onChange={handleInputChange}
                    onFocus={() => setFocusedInput('meetingTool')}
                    onBlur={() => setFocusedInput(null)}
                    style={getInputStyle('meetingTool')}
                  >
                    <option value="">Select your transcription tool</option>
                    <option value="fireflies">Fireflies.ai 🔥 (Direct Integration!)</option>
                    <option value="gong">Gong</option>
                    <option value="chorus">Chorus.ai</option>
                    <option value="otter">Otter.ai</option>
                    <option value="fathom">Fathom</option>
                    <option value="grain">Grain</option>
                    <option value="meetgeek">MeetGeek</option>
                    <option value="avoma">Avoma</option>
                    <option value="notta">Notta</option>
                    <option value="zoom-iq">Zoom IQ (with transcription)</option>
                    <option value="teams-transcription">Teams (with transcription)</option>
                    <option value="other">Other / Custom API</option>
                  </select>
                  {errors.meetingTool && <div style={styles.errorMessage}>{errors.meetingTool}</div>}
                  <div style={styles.helperText}>All these tools can send transcripts to our endpoint!</div>
                </div>

                <div style={styles.buttonGroup}>
                  <button
                    type="button"
                    onClick={previousStep}
                    style={{ ...styles.btn, ...styles.btnSecondary }}
                  >
                    ← Back
                  </button>
                  <button
                    type="button"
                    onClick={nextStep}
                    style={{ ...styles.btn, ...styles.btnPrimary }}
                  >
                    Almost There! →
                  </button>
                </div>
              </div>
            )}

            {/* Step 3: Preferences */}
            {currentStep === 3 && !isLoading && (
              <div style={styles.formStep}>
                <div style={styles.formGroup}>
                  <label style={styles.label}>How many meetings per week?</label>
                  <select
                    name="meetingsPerWeek"
                    value={formData.meetingsPerWeek}
                    onChange={handleInputChange}
                    onFocus={() => setFocusedInput('meetingsPerWeek')}
                    onBlur={() => setFocusedInput(null)}
                    style={getInputStyle('meetingsPerWeek')}
                  >
                    <option value="">Select range</option>
                    <option value="1-5">1-5 (Getting started)</option>
                    <option value="6-15">6-15 (Warming up)</option>
                    <option value="16-30">16-30 (On fire! 🔥)</option>
                    <option value="30+">30+ (Absolutely nuts! 🥜)</option>
                  </select>
                </div>

                <div style={styles.formGroup}>
                  <label style={styles.label}>Average deal cycle length?</label>
                  <select
                    name="dealCycle"
                    value={formData.dealCycle}
                    onChange={handleInputChange}
                    onFocus={() => setFocusedInput('dealCycle')}
                    onBlur={() => setFocusedInput(null)}
                    style={getInputStyle('dealCycle')}
                  >
                    <option value="">Select timeframe</option>
                    <option value="<1-week">Less than 1 week (Lightning fast!)</option>
                    <option value="1-4-weeks">1-4 weeks</option>
                    <option value="1-3-months">1-3 months</option>
                    <option value="3-6-months">3-6 months</option>
                    <option value="6+months">6+ months (Enterprise squirrel)</option>
                  </select>
                </div>

                <div style={styles.formGroup}>
                  <label style={styles.label}>Biggest follow-up challenge? (optional)</label>
                  <textarea
                    name="challenge"
                    value={formData.challenge}
                    onChange={handleInputChange}
                    onFocus={() => setFocusedInput('challenge')}
                    onBlur={() => setFocusedInput(null)}
                    style={{ ...getInputStyle('challenge'), minHeight: 80, resize: 'vertical' as const }}
                    placeholder="I spend 2 hours daily writing follow-ups and still forget half of them..."
                    rows={3}
                  />
                  <div style={styles.helperText}>Help us customize your experience!</div>
                </div>

                <div style={styles.checklist}>
                  <div style={styles.checklistItem}>
                    <span style={styles.checkIcon}>✓</span>
                    <span>14-day free trial with 500 acorns 🥜</span>
                  </div>
                  <div style={styles.checklistItem}>
                    <span style={styles.checkIcon}>✓</span>
                    <span>No credit card required</span>
                  </div>
                  <div style={styles.checklistItem}>
                    <span style={styles.checkIcon}>✓</span>
                    <span>Full access to all features</span>
                  </div>
                  <div style={styles.checklistItem}>
                    <span style={styles.checkIcon}>✓</span>
                    <span>Prompt templates included</span>
                  </div>
                  <div style={styles.checklistItem}>
                    <span style={styles.checkIcon}>✓</span>
                    <span>1-on-1 onboarding to help with setup</span>
                  </div>
                </div>

                <div style={styles.buttonGroup}>
                  <button
                    type="button"
                    onClick={previousStep}
                    style={{ ...styles.btn, ...styles.btnSecondary }}
                  >
                    ← Back
                  </button>
                  <button
                    type="submit"
                    style={{ ...styles.btn, ...styles.btnPrimary }}
                  >
                    Start Gathering Nuts! 🥜
                  </button>
                </div>
              </div>
            )}

            {/* Loading State */}
            {isLoading && (
              <div style={styles.loading}>
                <div style={styles.spinner} />
                <p style={styles.loadingText}>Setting up your tree...</p>
              </div>
            )}
          </form>
        </div>

        {/* Hero Section (Right Side) */}
        <div style={styles.heroSection} className="hero-section">
          <div style={styles.heroContent}>
            {/* Welcome Squirrel */}
            <div style={styles.squirrelWelcome}>
              <div style={styles.squirrelIcon}>🐿️</div>
              <h2 style={styles.welcomeTitle}>Welcome to Your New Superpower!</h2>
              <p style={styles.welcomeText}>
                In just 3 quick steps, you'll never write another follow-up manually.
                Start with <strong>500 free acorns</strong> (~166 sequences) to test the magic!
              </p>
            </div>

            {/* Social Proof */}
            <div style={styles.socialProof}>
              <p style={styles.proofQuote}>
                "Setup was incredibly fast. Used their prompt templates, tested with my transcript,
                and had my first sequence ready in under 10 minutes!"
              </p>
              <p style={styles.proofAuthor}>— Sarah Chen, Beta User</p>
            </div>

            {/* Stats */}
            <div style={styles.statsGrid}>
              <div style={styles.statCard}>
                <div style={styles.statNumber}>27 sec</div>
                <div style={styles.statLabel}>Avg sequence creation</div>
              </div>
              <div style={styles.statCard}>
                <div style={styles.statNumber}>43%</div>
                <div style={styles.statLabel}>Higher response rates</div>
              </div>
              <div style={styles.statCard}>
                <div style={styles.statNumber}>10+ hrs</div>
                <div style={styles.statLabel}>Saved per week</div>
              </div>
              <div style={styles.statCard}>
                <div style={styles.statNumber}>∞</div>
                <div style={styles.statLabel}>Squirrel puns</div>
              </div>
            </div>

            {/* Additional Trust Elements */}
            <div style={styles.trustBox}>
              <p style={{ color: colors.latte, fontSize: '0.875rem', marginBottom: '1rem' }}>
                <strong>🔒 Your data is safe</strong><br />
                End-to-end encryption. No squirrels reading your emails.
              </p>
              <p style={{ color: colors.latte, fontSize: '0.75rem' }}>
                Questions? <a href="mailto:hello@scurry.ai" style={{ color: colors.hyperOrange, textDecoration: 'none' }}>hello@scurry.ai</a>
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Responsive styles */}
      <style>{`
        @media (max-width: 968px) {
          .hero-section {
            display: none !important;
          }
        }
      `}</style>
    </div>
  )
}

export default RegisterPage
