import React, { useState } from 'react';
import { Box, Container, Typography, Accordion, AccordionSummary, AccordionDetails } from '@mui/material';
import { ChevronDown } from 'lucide-react';

const FAQS = [
  {
    q: 'How does SmartRoute AI eliminate surge pricing?',
    a: 'SmartRoute AI utilizes predictive Machine Learning to forecast rider demand per H3 spatial zone hours ahead. By pre-dispatching EV fleets and matching compatible riders along shared corridors, operational efficiency is maximized, allowing us to offer transparent flat fares 24/7 without surge multipliers.',
  },
  {
    q: 'What are Smart Pickup Points and how do they work?',
    a: 'Instead of forcing vehicles into congested side streets or narrow lanes, AI algorithms analyze nearby landmarks, well-lit sidewalks, and safe road bays within a 2-minute walk from your location. Picking up at a Smart Hub saves 4-8 minutes of detour time for everyone in the vehicle.',
  },
  {
    q: 'Is ride pooling safe and private with SmartRoute AI?',
    a: 'Yes! All vehicles in our network are verified Electric Vehicles with maximum 3 to 4 passengers per vehicle. Emergency SOS buttons, live telemetry tracking, and strict rider verification ensure top-tier safety and comfort.',
  },
  {
    q: 'How does pre-dispatch routing differ from legacy apps?',
    a: 'Traditional ride-hailing apps assign a driver and dynamically re-calculate routes mid-trip when traffic occurs. SmartRoute AI computes multi-stop graph optimizations BEFORE dispatching the vehicle, creating guaranteed time windows and smooth trajectories.',
  },
  {
    q: 'How is carbon reduction (CO₂ saved) calculated?',
    a: 'We measure the exact distance saved by pooling multiple riders into a single EV trip versus individual solo fuel trips. Your personal CO₂ savings counter updates automatically after every trip.',
  },
  {
    q: 'What payment methods are supported on SmartRoute AI?',
    a: 'We support all major payment options including UPI (Google Pay, PhonePe, Paytm), Credit/Debit Cards, SmartWallet balance, and Razorpay Checkout UI.',
  },
];

export const FAQSection = () => {
  const [expanded, setExpanded] = useState('panel-0');

  const handleChange = (panel) => (event, isExpanded) => {
    setExpanded(isExpanded ? panel : false);
  };

  return (
    <Box sx={{ py: { xs: 8, md: 12 }, position: 'relative' }}>
      <Container maxWidth="md">
        <Box sx={{ textAlign: 'center', mb: 6 }}>
          <Typography variant="caption" sx={{ color: '#00D4FF', fontWeight: 800, letterSpacing: '0.15em' }}>
            FREQUENTLY ASKED QUESTIONS
          </Typography>
          <Typography variant="h2" sx={{ fontWeight: 800, mt: 1 }}>
            Got Questions? We’ve Got Answers.
          </Typography>
        </Box>

        {FAQS.map((faq, idx) => {
          const panelId = `panel-${idx}`;
          return (
            <Accordion
              key={idx}
              expanded={expanded === panelId}
              onChange={handleChange(panelId)}
            >
              <AccordionSummary
                expandIcon={<ChevronDown color="#00D4FF" />}
                sx={{ px: 3, py: 1 }}
              >
                <Typography variant="h6" sx={{ fontWeight: 700, fontSize: '1.05rem' }}>
                  {faq.q}
                </Typography>
              </AccordionSummary>
              <AccordionDetails sx={{ px: 3, pb: 3, color: 'text.secondary', lineHeight: 1.7 }}>
                <Typography variant="body2">{faq.a}</Typography>
              </AccordionDetails>
            </Accordion>
          );
        })}
      </Container>
    </Box>
  );
};
