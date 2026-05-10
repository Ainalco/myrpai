import React, { useState, useRef, useCallback, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { authApi } from '@/lib/api'
import { useToast } from '@/components/ui/use-toast'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { Loader2, Mail, CheckCircle } from 'lucide-react'

interface EmailSignatureSettingsProps {
  initialSignature?: string
  initialEnabled?: boolean
}

/** Sanitize pasted HTML: strip scripts, iframes, event handlers */
function sanitizeHtml(html: string): string {
  const parser = new DOMParser()
  const doc = parser.parseFromString(html, 'text/html')

  // Remove dangerous elements
  doc.querySelectorAll('script, iframe, object, embed, form').forEach(el => el.remove())

  // Remove event handler attributes from all elements
  doc.querySelectorAll('*').forEach(el => {
    Array.from(el.attributes).forEach(attr => {
      if (attr.name.startsWith('on')) {
        el.removeAttribute(attr.name)
      }
    })
    // Remove javascript: URLs
    if (el.getAttribute('href')?.startsWith('javascript:')) {
      el.removeAttribute('href')
    }
    if (el.getAttribute('src')?.startsWith('javascript:')) {
      el.removeAttribute('src')
    }
  })

  return doc.body.innerHTML
}

const EmailSignatureSettings: React.FC<EmailSignatureSettingsProps> = ({
  initialSignature,
  initialEnabled,
}) => {
  const [enabled, setEnabled] = useState(initialEnabled ?? true)
  const [saved, setSaved] = useState(false)
  const editorRef = useRef<HTMLDivElement>(null)
  const { toast } = useToast()
  const queryClient = useQueryClient()

  // Sync initial values when they change (e.g. after fetch)
  useEffect(() => {
    if (initialEnabled !== undefined) setEnabled(initialEnabled)
  }, [initialEnabled])

  useEffect(() => {
    if (editorRef.current && initialSignature !== undefined) {
      editorRef.current.innerHTML = initialSignature
    }
  }, [initialSignature])

  const mutation = useMutation({
    mutationFn: (data: { email_signature?: string; email_signature_enabled?: boolean }) =>
      authApi.updateEmailSignature(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['currentUser'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
      toast({ title: 'Success', description: 'Email signature saved successfully' })
    },
    onError: (error: any) => {
      toast({
        title: 'Error',
        description: error.response?.data?.detail || 'Failed to save email signature',
        variant: 'destructive',
      })
    },
  })

  const handlePaste = useCallback((e: React.ClipboardEvent<HTMLDivElement>) => {
    const html = e.clipboardData.getData('text/html')
    if (html) {
      e.preventDefault()
      const clean = sanitizeHtml(html)
      document.execCommand('insertHTML', false, clean)
    }
  }, [])

  const handleSave = () => {
    const html = editorRef.current?.innerHTML || ''
    mutation.mutate({
      email_signature: html,
      email_signature_enabled: enabled,
    })
  }

  return (
    <Card className="border-scurry-gray-border">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Mail className="w-5 h-5 text-scurry-orange" />
            <CardTitle className="text-scurry-espresso">Email Signature</CardTitle>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm text-scurry-latte">
              {enabled ? 'Enabled' : 'Disabled'}
            </span>
            <Switch
              checked={enabled}
              onCheckedChange={setEnabled}
            />
          </div>
        </div>
        <CardDescription className="text-scurry-latte">
          Compose or paste your HTML email signature. It will be automatically appended to all outgoing emails when enabled.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Editor */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-scurry-espresso">Signature Editor</label>
          <div
            ref={editorRef}
            contentEditable
            onPaste={handlePaste}
            className="min-h-[120px] max-h-[300px] overflow-y-auto rounded-md border border-scurry-gray-border bg-white p-3 text-sm focus:outline-none focus:ring-2 focus:ring-scurry-orange/40 focus:border-scurry-orange"
            style={{ wordBreak: 'break-word' }}
          />
          <p className="text-xs text-scurry-gray-muted">
            You can type directly or paste a formatted signature from your email client. HTML formatting is preserved.
          </p>
        </div>

        {/* Live Preview */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-scurry-espresso">Preview</label>
          <div className="rounded-md border border-scurry-gray-border bg-scurry-foam p-4">
            <div className="text-xs text-scurry-gray-muted mb-2">— End of email body —</div>
            <div className="border-t border-scurry-gray-border pt-3">
              <SignaturePreview editorRef={editorRef} enabled={enabled} />
            </div>
          </div>
        </div>

        {/* Save Button */}
        <div className="flex items-center gap-3">
          <Button
            onClick={handleSave}
            disabled={mutation.isPending}
            className="bg-scurry-orange hover:bg-scurry-orange-hover"
          >
            {mutation.isPending ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Saving...
              </>
            ) : saved ? (
              <>
                <CheckCircle className="w-4 h-4 mr-2" />
                Saved!
              </>
            ) : (
              'Save Signature'
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

/** Live preview that mirrors the editor content */
function SignaturePreview({
  editorRef,
  enabled,
}: {
  editorRef: React.RefObject<HTMLDivElement | null>
  enabled: boolean
}) {
  const [html, setHtml] = useState('')

  useEffect(() => {
    if (!editorRef.current) return
    const el = editorRef.current

    const update = () => setHtml(el.innerHTML)
    update()

    const observer = new MutationObserver(update)
    observer.observe(el, { childList: true, subtree: true, characterData: true })

    el.addEventListener('input', update)
    return () => {
      observer.disconnect()
      el.removeEventListener('input', update)
    }
  }, [editorRef])

  if (!enabled) {
    return <p className="text-xs text-scurry-gray-muted italic">Signature is disabled</p>
  }

  if (!html || html === '<br>') {
    return <p className="text-xs text-scurry-gray-muted italic">No signature yet</p>
  }

  return <div className="text-sm" dangerouslySetInnerHTML={{ __html: html }} />
}

export default EmailSignatureSettings
